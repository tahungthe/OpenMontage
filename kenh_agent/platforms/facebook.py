"""Facebook Page qua Graph API.

Chuẩn bị (một lần): tạo app trên developers.facebook.com, lấy Page Access Token
dài hạn với quyền pages_manage_posts, pages_read_engagement,
pages_manage_engagement, pages_read_user_content, read_insights; điền vào `.env`:
    FB_PAGE_ID=...
    FB_PAGE_TOKEN=...
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from ..config import env
from .base import Platform

GRAPH = "https://graph.facebook.com/v21.0"
GRAPH_VIDEO = "https://graph-video.facebook.com/v21.0"


class Facebook(Platform):
    name = "facebook"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.page_id = env("FB_PAGE_ID")
        self.token = env("FB_PAGE_TOKEN")

    def is_connected(self) -> bool:
        return bool(self.page_id and self.token)

    def connect(self) -> None:
        if not self.is_connected():
            raise RuntimeError("Thiếu FB_PAGE_ID / FB_PAGE_TOKEN trong .env. Xem docs/kenh-agent/HUONG-DAN.md")
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
