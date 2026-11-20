"""Kết nối tới từng nền tảng. Mỗi lớp có cùng các hàm:

connect()            — đăng nhập lần đầu (mở trình duyệt khi cần)
is_connected()       — đã có token chưa
upload(post, video)  — đăng một bài, trả {"remote_id", "url"}
video_stats(ids)     — số liệu từng video
channel_stats()      — người theo dõi, tổng lượt xem
list_comments(ids)   — bình luận mới trên các video
reply(comment, text) — trả lời một bình luận
"""

from __future__ import annotations

from .base import Platform, DryRunPlatform  # noqa: F401


def get_platform(name: str, cfg: dict) -> "Platform":
    if cfg.get("dry_run"):
        return DryRunPlatform(name, cfg)
    if name == "youtube":
        from .youtube import YouTube
        return YouTube(cfg)
    if name == "facebook":
        from .facebook import Facebook
        return Facebook(cfg)
    if name == "tiktok":
        from .tiktok import TikTok
        return TikTok(cfg)
    raise ValueError(f"Nền tảng không hỗ trợ: {name}")


PLATFORMS = ("youtube", "tiktok", "facebook")
