"""Facebook Page qua Graph API.

Chuẩn bị (một lần): tạo app trên developers.facebook.com (use case "Quản lý mọi thứ
trên Trang"), điền vào `.env`:
    FB_APP_ID=...
    FB_APP_SECRET=...
rồi chạy `python -m kenh_agent connect facebook`: trình duyệt mở ra, bạn đăng nhập và
chọn Trang. Agent tự đổi sang token Trang không hết hạn và lưu ở kenh/agent/bi-mat/.
(Vẫn hỗ trợ cách cũ: điền thẳng FB_PAGE_ID / FB_PAGE_TOKEN trong `.env`.)
"""

from __future__ import annotations

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

GRAPH = "https://graph.facebook.com/v21.0"
GRAPH_VIDEO = "https://graph-video.facebook.com/v21.0"
REDIRECT = "http://localhost:8766/"
SCOPES = ("pages_show_list,pages_manage_posts,pages_read_engagement,pages_manage_engagement,"
          "pages_read_user_content,read_insights")


class Facebook(Platform):
    name = "facebook"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.page_file = SECRETS_DIR / "facebook-page.json"
        self.page_id = env("FB_PAGE_ID")
        self.token = env("FB_PAGE_TOKEN")
        if not (self.page_id and self.token) and self.page_file.exists():
            d = json.loads(self.page_file.read_text(encoding="utf-8"))
            self.page_id, self.token = d["page_id"], d["page_token"]

    def is_connected(self) -> bool:
        return bool(self.page_id and self.token)

    def connect(self, page_name: str | None = None) -> None:
        app_id, app_secret = env("FB_APP_ID"), env("FB_APP_SECRET")
        if not (app_id and app_secret):
            raise RuntimeError("Thiếu FB_APP_ID / FB_APP_SECRET trong .env. Xem docs/kenh-agent/HUONG-DAN.md")
        state = secrets.token_urlsafe(16)
        url = "https://www.facebook.com/v21.0/dialog/oauth?" + urllib.parse.urlencode({
            "client_id": app_id, "redirect_uri": REDIRECT, "state": state, "scope": SCOPES,
            "response_type": "code"})
        got: dict[str, str] = {}

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if "code" in q or "error" in q:
                    got.update({k: v[0] for k, v in q.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("Đã kết nối Facebook. Bạn có thể đóng tab này.".encode("utf-8"))

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("localhost", 8766), H)

        def serve():
            deadline = time.time() + 300
            srv.timeout = 5
            while not got and time.time() < deadline:
                srv.handle_request()

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        print("Mở trình duyệt để đăng nhập Facebook…")
        print(url)
        webbrowser.open(url)
        t.join(timeout=310)
        srv.server_close()
        if got.get("state") != state or "code" not in got:
            raise RuntimeError(f"Đăng nhập Facebook không thành công: {got}")

        def call(path, **params):
            r = requests.get(f"{GRAPH}/{path}", params=params, timeout=60)
            if not r.ok:
                raise RuntimeError(f"Facebook lỗi {r.status_code}: {r.text[:400]}")
            return r.json()

        short = call("oauth/access_token", client_id=app_id, client_secret=app_secret,
                     redirect_uri=REDIRECT, code=got["code"])["access_token"]
        long_user = call("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id,
                         client_secret=app_secret, fb_exchange_token=short)["access_token"]
        pages = call("me/accounts", access_token=long_user, fields="id,name,access_token", limit=100).get("data", [])
        if not pages:
            raise RuntimeError("Tài khoản này chưa quản lý Trang nào, hoặc chưa chọn Trang khi đăng nhập.")
        want = page_name or env("FB_PAGE_NAME")
        page = next((p for p in pages if want and want.lower() in p["name"].lower()), None)
        if page is None:
            if len(pages) > 1:
                names = ", ".join(p["name"] for p in pages)
                raise RuntimeError(f"Có nhiều Trang ({names}). Đặt FB_PAGE_NAME trong .env rồi chạy lại.")
            page = pages[0]
        # token Trang lấy từ token người dùng dài hạn => không hết hạn
        self.page_file.write_text(json.dumps({"page_id": page["id"], "page_name": page["name"],
                                              "page_token": page["access_token"]}, indent=2), encoding="utf-8")
        self.page_id, self.token = page["id"], page["access_token"]
        print("Đã kết nối Facebook:", self.channel_stats())

    def _get(self, path: str, **params) -> dict:
        params["access_token"] = self.token
        r = requests.get(f"{GRAPH}/{path}", params=params, timeout=60)
        if not r.ok:
            raise RuntimeError(f"Facebook lỗi {r.status_code}: {r.text[:400]}")
        return r.json()

    def _post(self, url: str, **kw) -> dict:
        r = requests.post(url, timeout=600, **kw)
        if not r.ok:
            raise RuntimeError(f"Facebook lỗi {r.status_code}: {r.text[:400]}")
        return r.json()

    # ---------- đăng bài ----------
    def upload(self, post: dict, video: dict) -> dict:
        if post.get("format") == "reel":
            return self._upload_reel(post)
        with open(post["file_path"], "rb") as f:
            data = self._post(
                f"{GRAPH_VIDEO}/{self.page_id}/videos",
                data={"access_token": self.token, "title": (post.get("title") or "")[:250],
                      "description": post.get("caption") or ""},
                files={"source": (os.path.basename(post["file_path"]), f, "video/mp4")},
            )
        vid = data["id"]
        return {"remote_id": vid, "url": f"https://www.facebook.com/{self.page_id}/videos/{vid}"}

    def _upload_reel(self, post: dict) -> dict:
        start = self._post(f"{GRAPH}/{self.page_id}/video_reels",
                           data={"upload_phase": "start", "access_token": self.token})
        vid = start["video_id"]
        size = os.path.getsize(post["file_path"])
        with open(post["file_path"], "rb") as f:
            r = requests.post(start["upload_url"], data=f, timeout=1200, headers={
                "Authorization": f"OAuth {self.token}", "offset": "0", "file_size": str(size)})
        if not r.ok:
            raise RuntimeError(f"Facebook Reel tải lên lỗi: {r.text[:400]}")
        self._post(f"{GRAPH}/{self.page_id}/video_reels", data={
            "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
            "description": post.get("caption") or "", "access_token": self.token})
        return {"remote_id": vid, "url": f"https://www.facebook.com/reel/{vid}"}

    # ---------- số liệu ----------
    def video_stats(self, remote_ids: list[str]) -> dict[str, dict]:
        out = {}
        for vid in remote_ids:
            try:
                d = self._get(vid, fields="views,comments.summary(true).limit(0),likes.summary(true).limit(0)")
                st = {"views": d.get("views"),
                      "comments": d.get("comments", {}).get("summary", {}).get("total_count"),
                      "likes": d.get("likes", {}).get("summary", {}).get("total_count")}
                try:
                    ins = self._get(f"{vid}/video_insights",
                                    metric="total_video_views,total_video_avg_time_watched,total_video_impressions")
                    for m in ins.get("data", []):
                        val = (m.get("values") or [{}])[0].get("value")
                        if m["name"] == "total_video_views":
                            st["views"] = val
                        elif m["name"] == "total_video_avg_time_watched" and val is not None:
                            st["avg_view_s"] = val / 1000
                except Exception:
                    pass
                out[vid] = st
            except Exception as e:
                print(f"Facebook: không lấy được số liệu {vid}: {e}")
        return out

    def channel_stats(self) -> dict:
        d = self._get(self.page_id, fields="name,followers_count,fan_count")
        return {"followers": d.get("followers_count") or d.get("fan_count"), "name": d.get("name")}

    # ---------- bình luận ----------
    def list_comments(self, remote_ids: list[str]) -> list[dict]:
        out = []
        for vid in remote_ids:
            try:
                d = self._get(f"{vid}/comments", fields="id,from,message,like_count,created_time,comments{from}",
                              filter="toplevel", order="reverse_chronological", limit=50)
            except Exception as e:
                print(f"Facebook: không đọc được bình luận {vid}: {e}")
                continue
            for c in d.get("data", []):
                if (c.get("from") or {}).get("id") == self.page_id:
                    continue
                replies = (c.get("comments") or {}).get("data", [])
                if any((r.get("from") or {}).get("id") == self.page_id for r in replies):
                    continue
                out.append({"remote_id": c["id"], "remote_video_id": vid,
                            "author": (c.get("from") or {}).get("name", "Người xem"),
                            "text": c.get("message", ""), "like_count": c.get("like_count", 0),
                            "created_at": c.get("created_time")})
            time.sleep(0.2)
        return out

    def reply(self, comment: dict, text: str) -> str:
        d = self._post(f"{GRAPH}/{comment['remote_id']}/comments",
                       data={"message": text, "access_token": self.token})
        return d["id"]
