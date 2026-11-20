"""TikTok Content Posting API + Display API.

Chuẩn bị (một lần): tạo app trên developers.tiktok.com, thêm sản phẩm
"Login Kit" và "Content Posting API" (bật Direct Post), scope:
user.info.basic, user.info.stats, video.list, video.upload, video.publish.
Redirect URI: http://localhost:8765/callback/  — điền vào `.env`:
    TIKTOK_CLIENT_KEY=...
    TIKTOK_CLIENT_SECRET=...
rồi chạy `python -m kenh_agent connect tiktok`.

Giới hạn của TikTok (không phải lỗi của agent):
- App chưa được TikTok duyệt (audit) chỉ đăng được ở chế độ riêng tư.
  Khi đó đặt `tiktok_che_do: inbox` để video vào hộp thư nháp, bạn bấm đăng trong app.
- API không cho đọc/trả lời bình luận với tài khoản thường → agent bỏ qua phần
  bình luận TikTok và ghi chú trong báo cáo.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from typing import Any

import requests

from ..config import SECRETS_DIR, env
from .base import Platform

API = "https://open.tiktokapis.com/v2"
SCOPES = "user.info.basic,user.info.stats,video.list,video.upload,video.publish"
REDIRECT = "http://localhost:8765/callback/"
CHUNK = 10 * 1024 * 1024


class TikTok(Platform):
    name = "tiktok"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.key = env("TIKTOK_CLIENT_KEY")
        self.secret = env("TIKTOK_CLIENT_SECRET")
        self.token_file = SECRETS_DIR / "tiktok-token.json"

    # ---------- đăng nhập ----------
    def is_connected(self) -> bool:
        return self.token_file.exists()

    def connect(self) -> None:
        if not (self.key and self.secret):
            raise RuntimeError("Thiếu TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET trong .env")
        state = secrets.token_urlsafe(16)
        # PKCE bắt buộc cho app Desktop. TikTok dùng SHA256 dạng hex (khác chuẩn base64url).
        verifier = secrets.token_urlsafe(64)[:64]
        challenge = hashlib.sha256(verifier.encode()).hexdigest()
        url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
            "client_key": self.key, "scope": SCOPES, "response_type": "code",
            "redirect_uri": REDIRECT, "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256"})
        got: dict[str, str] = {}

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if "code" in q or "error" in q:
                    got.update({k: v[0] for k, v in q.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("Đã kết nối TikTok. Bạn có thể đóng tab này.".encode("utf-8"))

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("localhost", 8765), H)
        def serve():
            deadline = time.time() + 300
            srv.timeout = 5
            while not got and time.time() < deadline:
                srv.handle_request()

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        print("Mở trình duyệt để đăng nhập TikTok…")
        webbrowser.open(url)
        t.join(timeout=310)
        srv.server_close()
        if got.get("state") != state or "code" not in got:
            raise RuntimeError(f"Đăng nhập TikTok không thành công: {got}")
        tok = requests.post(f"{API}/oauth/token/", data={
            "client_key": self.key, "client_secret": self.secret, "code": got["code"],
            "grant_type": "authorization_code", "redirect_uri": REDIRECT,
            "code_verifier": verifier}, timeout=60).json()
        if "access_token" not in tok:
            raise RuntimeError(f"TikTok không cấp token: {tok}")
        self._save(tok)
        print("Đã kết nối TikTok:", self.channel_stats())

    def _save(self, tok: dict) -> None:
        tok["obtained_at"] = int(time.time())
        self.token_file.write_text(json.dumps(tok, indent=2), encoding="utf-8")

    def _token(self) -> str:
        if not self.token_file.exists():
            raise RuntimeError("TikTok chưa kết nối. Chạy: python -m kenh_agent connect tiktok")
        tok = json.loads(self.token_file.read_text(encoding="utf-8"))
        if time.time() > tok["obtained_at"] + tok.get("expires_in", 86400) - 300:
            new = requests.post(f"{API}/oauth/token/", data={
                "client_key": self.key, "client_secret": self.secret, "grant_type": "refresh_token",
                "refresh_token": tok["refresh_token"]}, timeout=60).json()
            if "access_token" not in new:
                raise RuntimeError(f"TikTok hết hạn đăng nhập, cần chạy lại connect tiktok: {new}")
            self._save(new)
            tok = new
        return tok["access_token"]

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json; charset=UTF-8"}

    def _api(self, method: str, path: str, **kw) -> dict:
        r = requests.request(method, f"{API}{path}", headers=self._h(), timeout=120, **kw)
        data = r.json() if r.content else {}
        err = data.get("error", {})
        if not r.ok or (err and err.get("code") not in (None, "ok")):
            raise RuntimeError(f"TikTok lỗi {r.status_code}: {json.dumps(data, ensure_ascii=False)[:400]}")
        return data.get("data", {})

    # ---------- đăng bài ----------
    def upload(self, post: dict, video: dict) -> dict:
        path = post["file_path"]
        size = os.path.getsize(path)
        chunk = size if size <= CHUNK else CHUNK
        count = max(1, size // chunk)  # phần dư dồn vào khúc cuối (TikTok cho phép)
        source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count}
        mode = self.cfg.get("tiktok_che_do", "direct")
        if mode == "inbox":
            data = self._api("POST", "/post/publish/inbox/video/init/", json={"source_info": source})
        else:
            info = self._api("POST", "/post/publish/creator_info/query/")
            levels = info.get("privacy_level_options") or ["SELF_ONLY"]
            want = self.cfg.get("tiktok_quyen_rieng_tu", "PUBLIC_TO_EVERYONE")
            privacy = want if want in levels else levels[0]
            data = self._api("POST", "/post/publish/video/init/", json={
                "post_info": {"title": (post.get("caption") or post.get("title") or "")[:2100],
                              "privacy_level": privacy, "disable_comment": False,
                              "disable_duet": False, "disable_stitch": False,
                              "is_aigc": True},
                "source_info": source})
        publish_id, upload_url = data["publish_id"], data["upload_url"]
        with open(path, "rb") as f:
            for i in range(count):
                start = i * chunk
                end = size - 1 if i == count - 1 else start + chunk - 1
                f.seek(start)
                body = f.read(end - start + 1)
                r = requests.put(upload_url, data=body, timeout=600, headers={
                    "Content-Type": "video/mp4", "Content-Length": str(len(body)),
                    "Content-Range": f"bytes {start}-{end}/{size}"})
                if r.status_code not in (200, 201, 206):
                    raise RuntimeError(f"TikTok tải lên lỗi {r.status_code}: {r.text[:300]}")
        # chờ TikTok xử lý để lấy id bài đăng
        post_id = None
        for _ in range(40):
            time.sleep(15)
            st = self._api("POST", "/post/publish/status/fetch/", json={"publish_id": publish_id})
            status = st.get("status")
            if status == "FAILED":
                raise RuntimeError(f"TikTok từ chối video: {st.get('fail_reason')}")
            ids = st.get("publicaly_available_post_id") or st.get("publicly_available_post_id") or []
            if ids:
                post_id = str(ids[0])
                break
            if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                break
        rid = post_id or publish_id
        url = f"https://www.tiktok.com/video/{post_id}" if post_id else None
        return {"remote_id": rid, "url": url}

    # ---------- số liệu ----------
    def video_stats(self, remote_ids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        ids = [i for i in remote_ids if i.isdigit()]
        for i in range(0, len(ids), 20):
            d = self._api("POST", "/video/query/?fields=id,view_count,like_count,comment_count,share_count",
                          json={"filters": {"video_ids": ids[i:i + 20]}})
            for v in d.get("videos", []):
                out[str(v["id"])] = {"views": v.get("view_count"), "likes": v.get("like_count"),
                                     "comments": v.get("comment_count"), "shares": v.get("share_count")}
        return out

    def channel_stats(self) -> dict:
        d = self._api("GET", "/user/info/?fields=display_name,follower_count,likes_count,video_count")
        u = d.get("user", {})
        return {"followers": u.get("follower_count"), "video_count": u.get("video_count"),
                "likes": u.get("likes_count"), "name": u.get("display_name")}

    # ---------- bình luận ----------
    def list_comments(self, remote_ids: list[str]) -> list[dict]:
        return []  # TikTok API không mở bình luận cho tài khoản thường

    def reply(self, comment: dict, text: str) -> str:
        raise RuntimeError("TikTok API không hỗ trợ trả lời bình luận")


