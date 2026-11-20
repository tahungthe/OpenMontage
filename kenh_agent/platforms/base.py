from __future__ import annotations

import hashlib
import random
from typing import Any


class Platform:
    name = "base"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def is_connected(self) -> bool:
        raise NotImplementedError

    def connect(self) -> None:
        raise NotImplementedError

    def upload(self, post: dict, video: dict) -> dict:
        raise NotImplementedError

    def video_stats(self, remote_ids: list[str]) -> dict[str, dict]:
        raise NotImplementedError

    def channel_stats(self) -> dict:
        raise NotImplementedError

    def list_comments(self, remote_ids: list[str]) -> list[dict]:
        """Mỗi phần tử: {remote_id, remote_video_id, author, text, like_count, created_at}"""
        raise NotImplementedError

    def reply(self, comment: dict, text: str) -> str:
        raise NotImplementedError


class DryRunPlatform(Platform):
    """Giả lập để chạy thử toàn bộ quy trình mà không đụng tới tài khoản thật."""

    def __init__(self, name: str, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.name = name

    def is_connected(self) -> bool:
        return True

    def connect(self) -> None:
        print(f"[chạy thử] {self.name}: bỏ qua đăng nhập")

    def upload(self, post: dict, video: dict) -> dict:
        rid = "dry-" + hashlib.md5(f"{post['id']}{post['file_path']}".encode()).hexdigest()[:10]
        return {"remote_id": rid, "url": f"https://example.invalid/{self.name}/{rid}"}

    def video_stats(self, remote_ids: list[str]) -> dict[str, dict]:
        out = {}
        for rid in remote_ids:
            rnd = random.Random(rid)
            views = rnd.randint(200, 20000)
            out[rid] = {"views": views, "likes": views // rnd.randint(15, 40),
                        "comments": views // rnd.randint(80, 200), "shares": views // rnd.randint(100, 400),
                        "avg_view_pct": round(rnd.uniform(25, 70), 1)}
        return out

    def channel_stats(self) -> dict:
        return {"followers": 1000, "total_views": 50000, "video_count": 10}

    def list_comments(self, remote_ids: list[str]) -> list[dict]:
        if self.name == "tiktok":
            return []   # giống thật: TikTok không mở API bình luận
        out = []
        samples = ["Phim này tên gì vậy ad?", "Hay quá, ra phần tiếp đi ad ơi", "Kết phim buồn ghê",
                   "Review phim XYZ đi ad", "Giọng đọc cuốn quá"]
        for rid in remote_ids[:3]:
            rnd = random.Random(rid + "c")
            out.append({"remote_id": f"{rid}-c{rnd.randint(1, 99)}", "remote_video_id": rid,
                        "author": "Người xem thử", "text": rnd.choice(samples), "like_count": 0,
                        "created_at": None})
        return out

    def reply(self, comment: dict, text: str) -> str:
        return f"dry-reply-{comment['remote_id']}"
