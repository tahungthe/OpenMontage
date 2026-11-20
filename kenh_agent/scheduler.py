"""Chọn giờ đăng — bắt đầu từ "giờ vàng" mặc định cho khán giả Việt Nam,
rồi tự học từ số liệu thật: giờ nào cho lượt xem 48 giờ đầu cao hơn trung vị
của kênh thì được ưu tiên. Thỉnh thoảng thử giờ khác để không bỏ lỡ giờ tốt.
"""

from __future__ import annotations

import random
import statistics
from datetime import datetime, timedelta
from typing import Any

from .memory import iso, now_vn, parse_iso, rows


def hour_scores(platform: str) -> dict[int, float]:
    """Điểm mỗi giờ = trung bình (lượt xem ~48h / trung vị kênh) của các bài đăng giờ đó."""
    data = rows(
        """
        SELECT p.id, p.posted_at, MAX(m.views) AS views
        FROM posts p JOIN metrics m ON m.post_id = p.id
        WHERE p.platform = ? AND p.status = 'posted' AND m.hours_since_post BETWEEN 24 AND 96
        GROUP BY p.id
        """,
        (platform,),
    )
    views = [d["views"] or 0 for d in data]
    if len(views) < 5:
        return {}
    med = statistics.median(views) or 1
    by_hour: dict[int, list[float]] = {}
    for d in data:
        h = parse_iso(d["posted_at"]).hour
        by_hour.setdefault(h, []).append((d["views"] or 0) / med)
    return {h: statistics.mean(v) for h, v in by_hour.items() if len(v) >= 2}


def ranked_hours(platform: str, cfg: dict[str, Any]) -> list[int]:
    defaults = list(cfg["gio_vang"].get(platform, [20]))
    scores = hour_scores(platform)
    # giờ mặc định chưa có dữ liệu được điểm 1.0 (bằng trung vị)
    pool = {h: scores.get(h, 1.0) for h in set(defaults) | set(scores)}
    return sorted(pool, key=lambda h: pool[h], reverse=True)


def _taken(platform: str) -> list[datetime]:
    r = rows(
        "SELECT scheduled_at FROM posts WHERE platform=? AND status IN ('scheduled','posting','posted')",
        (platform,),
    )
    return [parse_iso(x["scheduled_at"]) for x in r]


def next_slot(platform: str, cfg: dict[str, Any], after: datetime | None = None) -> datetime:
    """Giờ đăng tốt nhất còn trống, sau thời điểm `after` (mặc định: 20 phút nữa)."""
    after = after or (now_vn() + timedelta(minutes=20))
    gap = timedelta(minutes=cfg["nhip_dang"]["khoang_cach_toi_thieu_phut"])
    taken = _taken(platform)
    hours = ranked_hours(platform, cfg)
    explore = random.random() < cfg.get("kham_pha_gio_moi", 0.2)
    if explore:
        # thử một giờ lân cận một giờ vàng để học thêm
        base = random.choice(hours[:3]) if hours else 20
        hours = [max(6, min(23, base + random.choice([-1, 1])))] + hours

    per_day = {
        "youtube": max(1, round(cfg["nhip_dang"]["youtube_full_moi_tuan"] / 7 + 0.49)),
        "tiktok": cfg["nhip_dang"]["tiktok_phan_moi_ngay"],
        "facebook": cfg["nhip_dang"]["facebook_bai_moi_ngay"],
    }.get(platform, 2)

    for day in range(0, 30):
        d = (after + timedelta(days=day)).date()
        same_day = [t for t in taken if t.date() == d]
        if len(same_day) >= per_day:
            continue
        for h in hours:
            minute = random.choice([0, 5, 10, 15, 20, 30])
            cand = datetime(d.year, d.month, d.day, h, minute, tzinfo=after.tzinfo)
            if cand <= after:
                continue
            if all(abs(cand - t) >= gap for t in taken):
                return cand
    return after + timedelta(hours=1)


def describe(platform: str, cfg: dict[str, Any]) -> str:
    scores = hour_scores(platform)
    if not scores:
        return f"{platform}: chưa đủ dữ liệu, đang dùng giờ vàng mặc định {cfg['gio_vang'].get(platform)}"
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:4]
    return f"{platform}: giờ tốt nhất theo số liệu " + ", ".join(f"{h}h (x{s:.2f})" for h, s in top)


__all__ = ["next_slot", "ranked_hours", "describe", "iso"]
