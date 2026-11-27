"""YouTube Data API v3 + YouTube Analytics API.

Chuẩn bị (một lần): tạo OAuth Client ID loại "Desktop app" trên Google Cloud,
bật "YouTube Data API v3" và "YouTube Analytics API", tải file JSON về
`kenh/agent/bi-mat/youtube-client.json`, rồi chạy `python -m kenh_agent connect youtube`.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..config import SECRETS_DIR, env
from .base import Platform

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


class YouTube(Platform):
    name = "youtube"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.client_file = Path(env("YOUTUBE_CLIENT_SECRET_FILE") or SECRETS_DIR / "youtube-client.json")
        self.token_file = SECRETS_DIR / "youtube-token.json"
        self._yt = None
        self._ya = None
        self._channel_id = None

    # ---------- đăng nhập ----------
    def _creds(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        if not self.token_file.exists():
            raise RuntimeError("YouTube chưa kết nối. Chạy: python -m kenh_agent connect youtube")
        creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def is_connected(self) -> bool:
        return self.token_file.exists()

    def connect(self) -> None:
        from google_auth_oauthlib.flow import InstalledAppFlow

        if not self.client_file.exists():
            raise RuntimeError(f"Thiếu file {self.client_file}. Xem hướng dẫn docs/kenh-agent/HUONG-DAN.md")
        flow = InstalledAppFlow.from_client_secrets_file(str(self.client_file), SCOPES)
        creds = flow.run_local_server(port=0, prompt="select_account consent", access_type="offline")
        self.token_file.write_text(creds.to_json(), encoding="utf-8")
        print("Đã kết nối YouTube:", self.channel_stats())

    @property
    def yt(self):
        if self._yt is None:
            from googleapiclient.discovery import build
            self._yt = build("youtube", "v3", credentials=self._creds(), cache_discovery=False)
        return self._yt

    @property
    def ya(self):
        if self._ya is None:
            from googleapiclient.discovery import build
            self._ya = build("youtubeAnalytics", "v2", credentials=self._creds(), cache_discovery=False)
        return self._ya

    def channel_id(self) -> str:
        if not self._channel_id:
            r = self.yt.channels().list(part="id", mine=True).execute()
            self._channel_id = r["items"][0]["id"]
        return self._channel_id

    # ---------- đăng bài ----------
    def upload(self, post: dict, video: dict) -> dict:
        from googleapiclient.http import MediaFileUpload

        tags = video.get("tags_list") or []
        meta = video.get("meta") or {}
        drama = bool(meta.get("nen_tang_phim"))   # tiếp thị liên kết phim ngắn — xem QUY-DINH-PHIM-NGAN.md
        lang = meta.get("ngon_ngu", "en" if drama else "vi")
        if drama:
            want = str((self.cfg.get("phim_ngan") or {}).get("kenh_youtube_id") or "").strip()
            if not want:
                raise RuntimeError("Video phim ngắn: chưa ghi phim_ngan.kenh_youtube_id (kênh đã báo cáo 报备 với "
                                   "bên phân phối) trong cau-hinh.yaml — không đăng")
            if self.channel_id() != want:
                raise RuntimeError(f"Video phim ngắn: YouTube đang kết nối kênh {self.channel_id()}, không phải kênh "
                                   f"đã báo cáo {want} — không đăng")
        body = {
            "snippet": {
                "title": (post.get("title") or video["title"])[:100],
                "description": (post.get("caption") or video.get("description") or "")[:4900],
                "tags": tags[:30],
                "categoryId": str(self.cfg.get("youtube_danh_muc", "1")),
                "defaultLanguage": lang,
                "defaultAudioLanguage": lang,
            },
            "status": {
                # Phim ngắn: luôn Không công khai, chờ mở khoá bản quyền (版权解锁) rồi mới công khai
                "privacyStatus": "unlisted" if drama else self.cfg.get("youtube_quyen_rieng_tu", "public"),
                "selfDeclaredMadeForKids": False,
                # Video có giọng đọc / hình AI tạo: khai báo nội dung tổng hợp theo chính sách YouTube
                "containsSyntheticMedia": True,
            },
        }
        media = MediaFileUpload(post["file_path"], chunksize=16 * 1024 * 1024, resumable=True, mimetype="video/mp4")
        part = "snippet,status"
        if drama:   # quảng bá có trả công (hoa hồng) -> khai báo paid promotion
            body["paidProductPlacementDetails"] = {"hasPaidProductPlacement": True}
            part += ",paidProductPlacementDetails"
        req = self.yt.videos().insert(part=part, body=body, media_body=media)
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        vid = resp["id"]
        thumb = video.get("thumbnail_path")
        if thumb and Path(thumb).exists() and post.get("format") == "full":
            try:
                self.yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb)).execute()
            except Exception as e:  # kênh chưa xác minh số điện thoại thì không đặt được thumbnail
                print("Không đặt được ảnh thumbnail:", e)
        return {"remote_id": vid, "url": f"https://www.youtube.com/watch?v={vid}"}

    def make_public(self, remote_id: str) -> None:
        """Chuyển video từ Không công khai sang Công khai (sau khi đã mở khoá bản quyền)."""
        r = self.yt.videos().list(part="status", id=remote_id).execute()
        if not r.get("items"):
            raise KeyError(f"Không thấy video YouTube {remote_id}")
        st = r["items"][0]["status"]
        st["privacyStatus"] = "public"
        st.pop("publishAt", None)
        self.yt.videos().update(part="status", body={"id": remote_id, "status": st}).execute()

    # ---------- số liệu ----------
    def video_stats(self, remote_ids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(remote_ids), 50):
            chunk = remote_ids[i:i + 50]
            r = self.yt.videos().list(part="statistics", id=",".join(chunk)).execute()
            for it in r.get("items", []):
                s = it["statistics"]
                out[it["id"]] = {"views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                                 "comments": int(s.get("commentCount", 0))}
        # tỉ lệ xem hết, thời gian xem, người đăng ký mới (Analytics API, trễ ~1-2 ngày)
        try:
            end = date.today()
            start = end - timedelta(days=90)
            for i in range(0, len(remote_ids), 200):
                chunk = remote_ids[i:i + 200]
                r = self.ya.reports().query(
                    ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
                    metrics="averageViewPercentage,averageViewDuration,estimatedMinutesWatched,subscribersGained,shares",
                    dimensions="video", filters="video==" + ",".join(chunk), maxResults=200,
                ).execute()
                for row in r.get("rows", []):
                    vid, pct, dur, mins, subs, shares = row
                    out.setdefault(vid, {}).update({"avg_view_pct": pct, "avg_view_s": dur,
                                                    "watch_time_min": mins, "subs_gained": subs, "shares": shares})
        except Exception as e:
            print("YouTube Analytics chưa lấy được:", e)
        return out

    def channel_stats(self) -> dict:
        r = self.yt.channels().list(part="statistics,snippet", mine=True).execute()
        it = r["items"][0]
        s = it["statistics"]
        return {"followers": int(s.get("subscriberCount", 0)), "total_views": int(s.get("viewCount", 0)),
                "video_count": int(s.get("videoCount", 0)), "name": it["snippet"]["title"]}

    # ---------- bình luận ----------
    def list_comments(self, remote_ids: list[str]) -> list[dict]:
        out = []
        my = self.channel_id()
        threads = []
        for vid in remote_ids:
            try:
                r = self.yt.commentThreads().list(part="snippet", videoId=vid, maxResults=50,
                                                  order="time", textFormat="plainText").execute()
                threads.extend(r.get("items", []))
            except Exception as e:  # video tắt bình luận / đã xoá
                print(f"Không đọc được bình luận video {vid}: {e}")
        for th in threads:
            top = th["snippet"]["topLevelComment"]
            sn = top["snippet"]
            if sn.get("authorChannelId", {}).get("value") == my:
                continue
            if th["snippet"].get("totalReplyCount", 0) and self._already_answered(th["id"], my):
                continue
            out.append({"remote_id": top["id"], "remote_video_id": th["snippet"].get("videoId"),
                        "author": sn.get("authorDisplayName"), "text": sn.get("textDisplay"),
                        "like_count": sn.get("likeCount", 0), "created_at": sn.get("publishedAt")})
        return out

    def _already_answered(self, thread_id: str, my_channel: str) -> bool:
        r = self.yt.comments().list(part="snippet", parentId=thread_id, maxResults=50).execute()
        return any(c["snippet"].get("authorChannelId", {}).get("value") == my_channel for c in r.get("items", []))

    def reply(self, comment: dict, text: str) -> str:
        r = self.yt.comments().insert(
            part="snippet", body={"snippet": {"parentId": comment["remote_id"], "textOriginal": text}}
        ).execute()
        return r["id"]

    # ---------- nghiên cứu thị trường ----------
    def search_market(self, query: str, days: int = 30, max_results: int = 50, region: str = "VN") -> list[dict]:
        from datetime import datetime, timezone

        after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = self.yt.search().list(part="snippet", q=query, type="video", order="viewCount", regionCode=region,
                                  relevanceLanguage="vi", publishedAfter=after, maxResults=min(max_results, 50)).execute()
        ids = [it["id"]["videoId"] for it in r.get("items", [])]
        if not ids:
            return []
        vids = self.yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids)).execute()["items"]
        ch_ids = list({v["snippet"]["channelId"] for v in vids})
        chans = self.yt.channels().list(part="statistics", id=",".join(ch_ids[:50])).execute()["items"]
        subs = {c["id"]: int(c["statistics"].get("subscriberCount", 0) or 0) for c in chans}
        out = []
        for v in vids:
            sn, st = v["snippet"], v["statistics"]
            out.append({
                "source": "youtube", "url": f"https://www.youtube.com/watch?v={v['id']}", "title": sn["title"],
                "channel": sn["channelTitle"], "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)), "published_at": sn["publishedAt"],
                "duration_s": _iso_duration(v["contentDetails"]["duration"]),
                "channel_subs": subs.get(sn["channelId"], 0),
            })
        return out


def _iso_duration(s: str) -> int:
    import re
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se
