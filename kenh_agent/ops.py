"""Các việc cụ thể của agent: ghi nhận video, cắt phần, lên lịch, đăng,
lấy số liệu, lấy/gửi bình luận, quét thị trường."""

from __future__ import annotations

import json
import statistics
import time
import traceback
from datetime import timedelta
from pathlib import Path
from typing import Any

from . import clipper, scheduler
from .config import AGENT_DIR, WORK_DIR
from .memory import connect, get_strategy, iso, log_event, now_vn, parse_iso, rows
from .platforms import PLATFORMS, get_platform

VIDEO_STORE = AGENT_DIR / "video"


# ---------------------------------------------------------------- video
COMPLIANCE_KEYS = ("ban_quyen", "nguyen_tac_cong_dong", "khong_gay_hieu_lam",
                   "khai_bao_ai", "ghi_cong_tac_pham", "phap_luat_vn")


def check_compliance(meta: dict) -> None:
    """Chặn video chưa qua kiểm tra tuân thủ (nền tảng, bản quyền, pháp luật)."""
    tt = meta.get("tuan_thu") or {}
    problems = []
    for k in COMPLIANCE_KEYS:
        item = tt.get(k)
        ok = item.get("ok") if isinstance(item, dict) else item
        note = item.get("ghi_chu", "") if isinstance(item, dict) else ""
        if ok is not True:
            problems.append(f"{k}: {'thiếu' if item is None else 'không đạt'}")
        elif not str(note).strip():
            problems.append(f"{k}: thiếu ghi chú đã kiểm tra thế nào")
    if problems:
        raise ValueError("Video chưa qua kiểm tra tuân thủ, không ghi nhận/xếp lịch: " + "; ".join(problems))


def register(meta_path: str | Path) -> dict:
    """Ghi nhận một video thành phẩm từ OpenMontage. `meta` là JSON agent viết (xem HUONG-DAN)."""
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    check_compliance(meta)
    src = Path(meta["full_path"])
    if not src.exists():
        raise FileNotFoundError(f"Không thấy video: {src}")
    slug = meta["slug"]
    store = VIDEO_STORE / slug
    store.mkdir(parents=True, exist_ok=True)
    (store / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    thumb = meta.get("thumbnail")
    with connect() as c:
        c.execute(
            """INSERT INTO videos(slug, title, film, full_path, description, tags, thumbnail_path, created_at, notes)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET title=excluded.title, film=excluded.film, full_path=excluded.full_path,
               description=excluded.description, tags=excluded.tags, thumbnail_path=excluded.thumbnail_path,
               notes=excluded.notes""",
            (slug, meta["title"], meta.get("film"), str(src), meta.get("description", ""),
             json.dumps(meta.get("tags", []), ensure_ascii=False), thumb, iso(now_vn()), meta.get("notes")),
        )
    log_event("video", f"Ghi nhận video {slug}")
    return get_video(slug)


def get_video(slug: str) -> dict:
    r = rows("SELECT * FROM videos WHERE slug=?", (slug,))
    if not r:
        raise KeyError(f"Chưa có video {slug}")
    v = r[0]
    v["tags_list"] = json.loads(v["tags"] or "[]")
    meta_file = VIDEO_STORE / slug / "meta.json"
    v["meta"] = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    return v


def split(slug: str, cfg: dict) -> list[dict]:
    v = get_video(slug)
    cuts = v["meta"].get("diem_cat")
    parts = clipper.split_video(v["full_path"], VIDEO_STORE / slug / "phan", v["title"], cfg, cuts=cuts)
    with connect() as c:
        c.execute("DELETE FROM parts WHERE video_id=?", (v["id"],))
        for p in parts:
            c.execute("INSERT INTO parts(video_id, idx, total, path, start_s, end_s, hook) VALUES (?,?,?,?,?,?,?)",
                      (v["id"], p["idx"], p["total"], p["path"], p["start_s"], p["end_s"], p["hook"]))
    log_event("split", f"Cắt {slug} thành {len(parts)} phần")
    return parts


def _facebook_format(video_id: int) -> str:
    mode = get_strategy("facebook_dinh_dang")
    if mode in ("full", "phan"):
        return mode
    return "full" if video_id % 2 else "phan"   # thử nghiệm xen kẽ cho tới khi có kết luận


def _part_caption(v: dict, idx: int, total: int, platform: str) -> str:
    meta = v["meta"]
    caps = meta.get("caption_phan") or []
    base = caps[idx - 1] if idx - 1 < len(caps) else f"{v['title']} | Phần {idx}/{total}"
    tags = " ".join(meta.get("hashtag") or [])
    follow = meta.get("loi_keu_goi_phan") or "Theo dõi kênh để xem phần tiếp theo!"
    if idx < total:
        base = f"{base}\n{follow}"
    return f"{base}\n{tags}".strip()


def queue(slug: str, cfg: dict, platforms: list[str] | None = None) -> list[dict]:
    """Lên lịch đăng cho một video trên các nền tảng, vào giờ tốt nhất còn trống."""
    v = get_video(slug)
    parts = rows("SELECT * FROM parts WHERE video_id=? ORDER BY idx", (v["id"],))
    platforms = platforms or list(PLATFORMS)
    meta = v["meta"]
    created = []

    def add(platform, fmt, path, title, caption, part_idx, after=None):
        when = scheduler.next_slot(platform, cfg, after=after)
        with connect() as c:
            cur = c.execute(
                """INSERT INTO posts(video_id, part_idx, platform, format, file_path, title, caption, scheduled_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (v["id"], part_idx, platform, fmt, path, title, caption, iso(when)))
            created.append({"id": cur.lastrowid, "platform": platform, "format": fmt, "part": part_idx,
                            "scheduled_at": iso(when)})
        return when

    if "youtube" in platforms:
        yt = meta.get("youtube", {})
        add("youtube", "full", v["full_path"], yt.get("title") or v["title"],
            yt.get("description") or v["description"], None)

    if parts and "tiktok" in platforms:
        prev = None
        for p in parts:   # các phần phải lên theo đúng thứ tự
            prev = add("tiktok", "phan", p["path"], f"{v['title']} - Phần {p['idx']}",
                       _part_caption(v, p["idx"], p["total"], "tiktok"), p["idx"], after=prev)

    if "facebook" in platforms:
        fmt = _facebook_format(v["id"])
        fb = meta.get("facebook", {})
        if fmt == "full" or not parts:
            add("facebook", "full", v["full_path"], fb.get("title") or v["title"],
                fb.get("description") or v["description"], None)
        else:
            prev = None
            for p in parts:
                prev = add("facebook", "reel", p["path"], f"{v['title']} - Phần {p['idx']}",
                           _part_caption(v, p["idx"], p["total"], "facebook"), p["idx"], after=prev)

    with connect() as c:
        c.execute("UPDATE videos SET status='queued' WHERE id=?", (v["id"],))
    log_event("queue", f"Lên lịch {len(created)} bài cho {slug}", created)
    return created


def publish_due(cfg: dict, limit: int = 5) -> list[dict]:
    """Đăng các bài đã tới giờ. Chạy định kỳ (15 phút/lần) bởi Task Scheduler."""
    due = rows(
        "SELECT * FROM posts WHERE status IN ('scheduled','failed') AND attempts < 3 AND scheduled_at <= ? "
        "ORDER BY scheduled_at LIMIT ?", (iso(now_vn()), limit))
    results = []
    for p in due:
        plat = get_platform(p["platform"], cfg)
        if not plat.is_connected():
            results.append({"id": p["id"], "status": "skipped", "error": "chưa kết nối"})
            continue
        # TikTok/FB phần sau chỉ đăng khi phần trước đã lên
        if p["part_idx"] and p["part_idx"] > 1:
            prev = rows("SELECT status FROM posts WHERE video_id=? AND platform=? AND part_idx=?",
                        (p["video_id"], p["platform"], p["part_idx"] - 1))
            if prev and prev[0]["status"] != "posted":
                continue
        with connect() as c:
            c.execute("UPDATE posts SET status='posting', attempts=attempts+1 WHERE id=?", (p["id"],))
        video = get_video(rows("SELECT slug FROM videos WHERE id=?", (p["video_id"],))[0]["slug"])
        try:
            res = plat.upload(p, video)
            with connect() as c:
                c.execute("UPDATE posts SET status='posted', remote_id=?, url=?, posted_at=?, error=NULL WHERE id=?",
                          (res["remote_id"], res.get("url"), iso(now_vn()), p["id"]))
            log_event("posted", f"{p['platform']} #{p['id']} đã đăng", res)
            results.append({"id": p["id"], "status": "posted", **res})
        except Exception as e:
            err = f"{e}"[:800]
            with connect() as c:
                c.execute("UPDATE posts SET status='failed', error=? WHERE id=?", (err, p["id"]))
            log_event("error", f"{p['platform']} #{p['id']} lỗi khi đăng", {"error": err, "tb": traceback.format_exc()[-1500:]})
            results.append({"id": p["id"], "status": "failed", "error": err})
    # video đã lên đủ mọi nơi
    with connect() as c:
        c.execute("""UPDATE videos SET status='published' WHERE status='queued' AND id NOT IN
                     (SELECT video_id FROM posts WHERE status NOT IN ('posted','cancelled'))""")
    return results


def reschedule(post_id: int, cfg: dict, when: str | None = None) -> str:
    p = rows("SELECT * FROM posts WHERE id=?", (post_id,))[0]
    dt = parse_iso(when) if when else scheduler.next_slot(p["platform"], cfg)
    with connect() as c:
        c.execute("UPDATE posts SET scheduled_at=?, status='scheduled', attempts=0 WHERE id=?", (iso(dt), post_id))
    return iso(dt)


# ---------------------------------------------------------------- số liệu
def pull_analytics(cfg: dict, days: int = 45) -> dict:
    since = iso(now_vn() - timedelta(days=days))
    summary: dict[str, Any] = {}
    for name in PLATFORMS:
        plat = get_platform(name, cfg)
        if not plat.is_connected():
            summary[name] = "chưa kết nối"
            continue
        posts = rows("SELECT * FROM posts WHERE platform=? AND status='posted' AND posted_at>=? AND remote_id IS NOT NULL",
                     (name, since))
        try:
            stats = plat.video_stats([p["remote_id"] for p in posts]) if posts else {}
        except Exception as e:
            summary[name] = f"lỗi: {e}"
            log_event("error", f"{name}: lỗi lấy số liệu", str(e))
            continue
        now = now_vn()
        with connect() as c:
            for p in posts:
                s = stats.get(p["remote_id"])
                if not s:
                    continue
                hrs = (now - parse_iso(p["posted_at"])).total_seconds() / 3600
                c.execute(
                    """INSERT INTO metrics(post_id, captured_at, hours_since_post, views, likes, comments, shares,
                       avg_view_pct, avg_view_s, watch_time_min, subs_gained, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (p["id"], iso(now), round(hrs, 1), s.get("views"), s.get("likes"), s.get("comments"),
                     s.get("shares"), s.get("avg_view_pct"), s.get("avg_view_s"), s.get("watch_time_min"),
                     s.get("subs_gained"), json.dumps(s, ensure_ascii=False)))
            try:
                ch = plat.channel_stats()
                c.execute("INSERT INTO channel_metrics(platform, captured_at, followers, total_views, video_count, raw) "
                          "VALUES (?,?,?,?,?,?)", (name, iso(now), ch.get("followers"), ch.get("total_views"),
                                                   ch.get("video_count"), json.dumps(ch, ensure_ascii=False)))
            except Exception as e:
                ch = {"error": str(e)}
        summary[name] = {"bai_cap_nhat": len(stats), "kenh": ch}
    log_event("analytics", "Cập nhật số liệu", summary)
    return summary


# ---------------------------------------------------------------- bình luận
def fetch_comments(cfg: dict, days: int = 14) -> Path:
    since = iso(now_vn() - timedelta(days=days))
    for name in PLATFORMS:
        plat = get_platform(name, cfg)
        if not plat.is_connected():
            continue
        posts = rows("SELECT id, remote_id FROM posts WHERE platform=? AND status='posted' AND posted_at>=?",
                     (name, since))
        by_remote = {p["remote_id"]: p["id"] for p in posts if p["remote_id"]}
        if not by_remote:
            continue
        try:
            items = plat.list_comments(list(by_remote))
        except Exception as e:
            log_event("error", f"{name}: lỗi đọc bình luận", str(e))
            continue
        with connect() as c:
            for it in items:
                c.execute(
                    """INSERT OR IGNORE INTO comments(platform, remote_id, post_id, remote_video_id, author, text,
                       like_count, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                    (name, it["remote_id"], by_remote.get(it.get("remote_video_id")), it.get("remote_video_id"),
                     it.get("author"), it.get("text"), it.get("like_count"), it.get("created_at")))
    pending = rows(
        """SELECT cm.platform, cm.remote_id, cm.author, cm.text, cm.like_count, cm.created_at,
                  v.title AS video_title, v.film, p.part_idx
           FROM comments cm LEFT JOIN posts p ON p.id = cm.post_id LEFT JOIN videos v ON v.id = p.video_id
           WHERE cm.status='new' ORDER BY cm.like_count DESC, cm.created_at DESC LIMIT ?""",
        (cfg["binh_luan"]["tra_loi_toi_da_moi_lan"],))
    out = WORK_DIR / "binh-luan-can-tra-loi.json"
    out.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def send_replies(replies_path: str | Path, cfg: dict) -> dict:
    """File JSON: [{"platform","remote_id","reply": "..."} | {"platform","remote_id","skip": true}]"""
    items = json.loads(Path(replies_path).read_text(encoding="utf-8"))
    done = skipped = failed = 0
    for it in items:
        key = (it["platform"], it["remote_id"])
        if it.get("skip") or not it.get("reply"):
            with connect() as c:
                c.execute("UPDATE comments SET status='skipped', replied_at=? WHERE platform=? AND remote_id=?",
                          (iso(now_vn()), *key))
            skipped += 1
            continue
        try:
            rid = get_platform(it["platform"], cfg).reply({"remote_id": it["remote_id"]}, it["reply"].strip())
            with connect() as c:
                c.execute("UPDATE comments SET status='replied', reply_text=?, replied_at=?, reply_remote_id=? "
                          "WHERE platform=? AND remote_id=?", (it["reply"], iso(now_vn()), rid, *key))
            done += 1
            time.sleep(2 if not cfg.get("dry_run") else 0)   # đừng trả lời dồn dập như máy
        except Exception as e:
            failed += 1
            log_event("error", f"Trả lời bình luận lỗi {key}", str(e))
    res = {"da_tra_loi": done, "bo_qua": skipped, "loi": failed}
    log_event("comments", "Trả lời bình luận", res)
    return res


# ---------------------------------------------------------------- thị trường
def market_scan(cfg: dict, queries: list[str], days: int = 30) -> Path:
    """Quét YouTube tìm video review phim đang lên mạnh (cần kết nối YouTube)."""
    from .platforms.youtube import YouTube

    yt = YouTube(cfg)
    if not yt.is_connected():
        raise RuntimeError("Cần kết nối YouTube để quét thị trường (python -m kenh_agent connect youtube)")
    found = []
    for q in queries:
        found += yt.search_market(q, days=days)
    now = now_vn()
    for f in found:
        age_days = max(0.5, (now - parse_iso(f["published_at"])).total_seconds() / 86400)
        f["views_per_day"] = round(f["views"] / age_days, 1)
        f["outlier_score"] = round(f["views"] / max(1000, f["channel_subs"]), 2)
    with connect() as c:
        for f in found:
            c.execute(
                """INSERT INTO research(captured_at, source, url, title, channel, views, likes, comments, published_at,
                   duration_s, channel_subs, views_per_day, outlier_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(url) DO UPDATE SET views=excluded.views, likes=excluded.likes,
                   comments=excluded.comments, views_per_day=excluded.views_per_day,
                   outlier_score=excluded.outlier_score, captured_at=excluded.captured_at""",
                (iso(now), f["source"], f["url"], f["title"], f["channel"], f["views"], f["likes"], f["comments"],
                 f["published_at"], f["duration_s"], f["channel_subs"], f["views_per_day"], f["outlier_score"]))
    found.sort(key=lambda f: (f["outlier_score"], f["views_per_day"]), reverse=True)
    out = WORK_DIR / f"thi-truong-{now:%Y-%m-%d}.json"
    out.write_text(json.dumps(found[:80], ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# ---------------------------------------------------------------- tổng hợp cho agent
def performance_table(days: int = 7) -> list[dict]:
    """Số liệu mới nhất của từng bài đăng trong `days` ngày (dùng cho báo cáo & phân tích tuần)."""
    since = iso(now_vn() - timedelta(days=days))
    data = rows(
        """SELECT p.id, p.platform, p.format, p.part_idx, p.posted_at, p.url, v.slug, v.title, v.film,
                  m.views, m.likes, m.comments, m.shares, m.avg_view_pct, m.avg_view_s, m.subs_gained, m.hours_since_post
           FROM posts p JOIN videos v ON v.id = p.video_id
           LEFT JOIN metrics m ON m.id = (SELECT id FROM metrics WHERE post_id = p.id ORDER BY captured_at DESC LIMIT 1)
           WHERE p.status='posted' AND p.posted_at >= ? ORDER BY p.posted_at""", (since,))
    for name in PLATFORMS:
        vs = [d["views"] or 0 for d in data if d["platform"] == name]
        med = statistics.median(vs) if vs else 0
        for d in data:
            if d["platform"] == name:
                d["so_voi_trung_vi"] = round((d["views"] or 0) / med, 2) if med else None
    return data


def facebook_format_verdict(min_each: int = 4) -> dict:
    """So sánh Facebook đăng full vs từng phần: lượt xem trung bình mỗi video gốc."""
    data = rows(
        """SELECT p.video_id, p.format, MAX(m.views) AS views
           FROM posts p JOIN metrics m ON m.post_id = p.id
           WHERE p.platform='facebook' AND p.status='posted' AND m.hours_since_post >= 48
           GROUP BY p.id""")
    per_video: dict[tuple[int, str], int] = {}
    for d in data:
        k = (d["video_id"], "full" if d["format"] == "full" else "phan")
        per_video[k] = per_video.get(k, 0) + (d["views"] or 0)
    full = [v for (vid, f), v in per_video.items() if f == "full"]
    phan = [v for (vid, f), v in per_video.items() if f == "phan"]
    res = {"so_video_full": len(full), "so_video_phan": len(phan),
           "tb_full": round(statistics.mean(full)) if full else None,
           "tb_phan": round(statistics.mean(phan)) if phan else None, "ket_luan": None}
    if len(full) >= min_each and len(phan) >= min_each:
        res["ket_luan"] = "full" if res["tb_full"] >= res["tb_phan"] * 1.1 else (
            "phan" if res["tb_phan"] >= res["tb_full"] * 1.1 else "chua-ro")
    return res

