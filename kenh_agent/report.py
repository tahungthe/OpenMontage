"""Báo cáo ngày (tự động, từ số liệu) và gói dữ liệu tuần (để agent phân tích).

Báo cáo lưu ở kenh/agent/bao-cao/. Nếu bật Telegram trong cấu hình và điền
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID trong .env thì gửi luôn vào điện thoại.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import requests

from . import ops, scheduler
from .config import REPORTS_DIR, env
from .memory import iso, now_vn, rows
from .platforms import PLATFORMS

TEN = {"youtube": "YouTube", "tiktok": "TikTok", "facebook": "Facebook"}


def _fmt(n) -> str:
    return "—" if n is None else f"{int(n):,}".replace(",", ".")


def _followers_delta(platform: str, hours: int) -> tuple[int | None, int | None]:
    now = rows("SELECT followers FROM channel_metrics WHERE platform=? ORDER BY captured_at DESC LIMIT 1", (platform,))
    old = rows("SELECT followers FROM channel_metrics WHERE platform=? AND captured_at <= ? "
               "ORDER BY captured_at DESC LIMIT 1", (platform, iso(now_vn() - timedelta(hours=hours))))
    cur = now[0]["followers"] if now else None
    prev = old[0]["followers"] if old else None
    return cur, (cur - prev if cur is not None and prev is not None else None)


def daily(cfg: dict, extra_notes: str = "") -> Path:
    t = now_vn()
    since = iso(t - timedelta(hours=24))
    lines = [f"# Báo cáo kênh ngày {t:%d/%m/%Y}", ""]
    if cfg.get("dry_run"):
        lines += ["> **Đang chạy thử** — chưa đăng thật. Số liệu dưới đây là giả lập.", ""]

    lines += ["## Người theo dõi", "", "| Nền tảng | Hiện có | 24 giờ qua | 7 ngày qua |", "|---|---|---|---|"]
    for p in PLATFORMS:
        cur, d1 = _followers_delta(p, 24)
        _, d7 = _followers_delta(p, 24 * 7)
        sign = lambda x: "—" if x is None else (f"+{x}" if x >= 0 else str(x))  # noqa: E731
        lines.append(f"| {TEN[p]} | {_fmt(cur)} | {sign(d1)} | {sign(d7)} |")

    posted = rows("""SELECT p.*, v.title AS vtitle FROM posts p JOIN videos v ON v.id=p.video_id
                     WHERE p.status='posted' AND p.posted_at>=? ORDER BY p.posted_at""", (since,))
    lines += ["", f"## Đã đăng trong 24 giờ qua ({len(posted)} bài)", ""]
    for p in posted:
        part = f" — phần {p['part_idx']}" if p["part_idx"] else " — bản full"
        lines.append(f"- {p['posted_at'][11:16]} **{TEN[p['platform']]}**: {p['vtitle'].replace('|', '-')}{part} {p['url'] or ''}")
    if not posted:
        lines.append("- (không có)")

    perf = [d for d in ops.performance_table(days=7) if d["views"] is not None]
    perf.sort(key=lambda d: d["views"] or 0, reverse=True)
    lines += ["", "## Bài nổi bật 7 ngày", "", "| Nền tảng | Video | Lượt xem | Thích | Bình luận | Xem trung bình |",
              "|---|---|---|---|---|---|"]
    for d in perf[:8]:
        part = f" (P{d['part_idx']})" if d["part_idx"] else ""
        watch = f"{d['avg_view_pct']:.0f}%" if d.get("avg_view_pct") else (
            f"{d['avg_view_s']:.0f}s" if d.get("avg_view_s") else "—")
        lines.append(f"| {TEN[d['platform']]} | {d['title'].split('|')[0].strip()[:45]}{part} | {_fmt(d['views'])} | {_fmt(d['likes'])} | "
                     f"{_fmt(d['comments'])} | {watch} |")

    c = rows("SELECT status, COUNT(*) n FROM comments WHERE COALESCE(replied_at, created_at, '') >= ? GROUP BY status",
             (since,))
    cm = {r["status"]: r["n"] for r in c}
    lines += ["", "## Bình luận", "",
              f"- Đã trả lời: {cm.get('replied', 0)} · Bỏ qua (spam/không cần): {cm.get('skipped', 0)} · "
              f"Đang chờ: {rows('SELECT COUNT(*) n FROM comments WHERE status=?', ('new',))[0]['n']}",
              "- TikTok không cho phép đọc/trả lời bình luận qua API: phần này cần bạn xem trong app."]

    upcoming = rows("""SELECT p.platform, p.scheduled_at, p.part_idx, v.title FROM posts p JOIN videos v ON v.id=p.video_id
                       WHERE p.status='scheduled' ORDER BY p.scheduled_at LIMIT 12""")
    lines += ["", "## Lịch đăng sắp tới", ""]
    for u in upcoming:
        part = f" (phần {u['part_idx']})" if u["part_idx"] else " (full)"
        lines.append(f"- {u['scheduled_at'][5:16].replace('T', ' ')} {TEN[u['platform']]}: {u['title']}{part}")
    if not upcoming:
        lines.append("- Hàng đợi trống — agent sẽ làm video mới.")

    errs = rows("SELECT at, message FROM events WHERE kind='error' AND at>=? ORDER BY at DESC LIMIT 8", (since,))
    failed = rows("SELECT id, platform, error FROM posts WHERE status='failed'")
    if errs or failed:
        lines += ["", "## Sự cố cần chú ý", ""]
        lines += [f"- {e['at'][11:16]} {e['message']}" for e in errs]
        lines += [f"- Bài #{f['id']} ({TEN[f['platform']]}) đăng lỗi: {(f['error'] or '')[:160]}" for f in failed]

    lines += ["", "## Giờ đăng đang áp dụng", ""] + [f"- {scheduler.describe(p, cfg)}" for p in PLATFORMS]
    if extra_notes.strip():
        lines += ["", "## Ghi chú của agent", "", extra_notes.strip()]

    out = REPORTS_DIR / f"ngay-{t:%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if cfg.get("bao_cao", {}).get("telegram"):
        send_telegram(out)
    return out


def weekly_data(days: int = 7) -> Path:
    """Gói số liệu tuần thành JSON để agent đọc và viết phân tích + bài học."""
    t = now_vn()
    data = {
        "tu_ngay": iso(t - timedelta(days=days)), "den_ngay": iso(t),
        "bai_dang": ops.performance_table(days=days),
        "bai_dang_4_tuan": ops.performance_table(days=28),
        "nguoi_theo_doi": {p: _followers_delta(p, 24 * days) for p in PLATFORMS},
        "facebook_full_hay_phan": ops.facebook_format_verdict(),
        "gio_dang": {p: scheduler.hour_scores(p) for p in PLATFORMS},
        "binh_luan_tuan": rows("""SELECT platform, text, like_count, reply_text FROM comments
                                  WHERE created_at >= ? OR replied_at >= ? ORDER BY like_count DESC LIMIT 150""",
                               (iso(t - timedelta(days=days)),) * 2),
        "thi_truong": rows("""SELECT title, channel, url, views, views_per_day, outlier_score, published_at
                              FROM research WHERE captured_at >= ? ORDER BY outlier_score DESC LIMIT 40""",
                           (iso(t - timedelta(days=days)),)),
        "chien_luoc_hien_tai": rows("SELECT * FROM strategy"),
    }
    out = REPORTS_DIR / f"du-lieu-tuan-{t:%Y-%m-%d}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out


def send_telegram(path: Path) -> bool:
    token, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    text = path.read_text(encoding="utf-8")
    for i in range(0, len(text), 3900):
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text[i:i + 3900]}, timeout=30)
    return True
