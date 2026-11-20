"""Bảng điều khiển dòng lệnh của agent kênh.

    python -m kenh_agent status
    python -m kenh_agent connect youtube|facebook|tiktok
    python -m kenh_agent register kenh/agent/viec/<slug>.json
    python -m kenh_agent split <slug>
    python -m kenh_agent queue <slug> [--platforms youtube tiktok facebook]
    python -m kenh_agent publish-due
    python -m kenh_agent analytics
    python -m kenh_agent comments fetch | comments reply <file.json>
    python -m kenh_agent market "review phim" "tóm tắt phim" ...
    python -m kenh_agent report daily [--notes FILE] | report weekly-data
    python -m kenh_agent strategy [KEY VALUE --reason ...]
    python -m kenh_agent mode test|live
    python -m kenh_agent install-poster
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import ops, report
from .config import AGENT_DIR, CONFIG_PATH, LEARNINGS_PATH, REPO_ROOT, load_config
from .memory import rows, set_strategy
from .platforms import PLATFORMS, get_platform

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

LEARNINGS_TEMPLATE = """# Bài học của agent quản lý kênh

_Agent tự cập nhật file này sau mỗi lần phân tích tuần. Mỗi bài học ghi: điều rút ra, bằng chứng (số liệu), ngày._

## Nội dung / phim nào hút người xem

## Hook, tiêu đề, thumbnail

## Độ dài và cách cắt phần

## Giờ đăng

## Facebook: full hay từng phần

## Bình luận: người xem hỏi gì, thích gì

## Sai lầm không lặp lại
"""


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_status(cfg) -> None:
    out = {"che_do": "CHẠY THỬ (không đăng thật)" if cfg["dry_run"] else "THẬT", "cau_hinh": str(CONFIG_PATH)}
    conn = {}
    for p in PLATFORMS:
        real = get_platform(p, {**cfg, "dry_run": False})
        try:
            conn[p] = "đã kết nối" if real.is_connected() else "chưa kết nối"
        except Exception as e:
            conn[p] = f"lỗi: {e}"
    out["ket_noi"] = conn
    out["video"] = rows("SELECT status, COUNT(*) n FROM videos GROUP BY status")
    out["bai_dang"] = rows("SELECT platform, status, COUNT(*) n FROM posts GROUP BY platform, status")
    out["sap_dang"] = rows("SELECT id, platform, part_idx, scheduled_at FROM posts WHERE status='scheduled' "
                           "ORDER BY scheduled_at LIMIT 10")
    out["binh_luan_cho"] = rows("SELECT COUNT(*) n FROM comments WHERE status='new'")[0]["n"]
    _print(out)


def cmd_install_poster() -> None:
    """Đăng ký Task Scheduler của Windows: 15 phút/lần chạy publish-due (không tốn AI)."""
    py = REPO_ROOT / ".venv" / "Scripts" / "pythonw.exe"   # pythonw: chạy ẩn, không bật cửa sổ đen
    if not py.exists():
        py = Path(sys.executable)
    launcher = AGENT_DIR / "dang-bai.pyw"
    launcher.write_text(
        "import sys, os, datetime\n"
        f"sys.path.insert(0, r'{REPO_ROOT}')\n"
        f"os.chdir(r'{REPO_ROOT}')\n"
        f"log = open(r'{AGENT_DIR / 'dang-bai.log'}', 'a', encoding='utf-8')\n"
        "sys.stdout = sys.stderr = log\n"
        "try:\n"
        "    from kenh_agent.__main__ import main\n"
        "    main(['publish-due'])\n"
        "except Exception:\n"
        "    import traceback; print(datetime.datetime.now(), traceback.format_exc())\n",
        encoding="utf-8")
    old_bat = AGENT_DIR / "dang-bai.cmd"
    if old_bat.exists():
        old_bat.unlink()
    cmd = ["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", "15", "/TN", "KenhAgent-DangBai",
           "/TR", f'"{py}" "{launcher}"']
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout or r.stderr)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="kenh_agent", description="Agent quản lý kênh YouTube/TikTok/Facebook")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("init")
    c = sub.add_parser("connect"); c.add_argument("platform", choices=PLATFORMS)
    c = sub.add_parser("register"); c.add_argument("meta")
    c = sub.add_parser("split"); c.add_argument("slug")
    c = sub.add_parser("queue"); c.add_argument("slug"); c.add_argument("--platforms", nargs="*")
    sub.add_parser("publish-due")
    c = sub.add_parser("reschedule"); c.add_argument("post_id", type=int); c.add_argument("--at")
    c = sub.add_parser("cancel"); c.add_argument("post_id", type=int)
    sub.add_parser("analytics")
    c = sub.add_parser("comments"); c.add_argument("action", choices=["fetch", "reply"]); c.add_argument("file", nargs="?")
    c = sub.add_parser("market"); c.add_argument("queries", nargs="+"); c.add_argument("--days", type=int, default=30)
    c = sub.add_parser("report"); c.add_argument("kind", choices=["daily", "weekly-data"]); c.add_argument("--notes")
    c = sub.add_parser("strategy"); c.add_argument("key", nargs="?"); c.add_argument("value", nargs="?"); c.add_argument("--reason", default="")
    c = sub.add_parser("mode"); c.add_argument("which", choices=["test", "live"])
    sub.add_parser("install-poster")
    a = ap.parse_args(argv)
    cfg = load_config()

    if a.cmd == "init" or not LEARNINGS_PATH.exists():
        if not LEARNINGS_PATH.exists():
            LEARNINGS_PATH.write_text(LEARNINGS_TEMPLATE, encoding="utf-8")
        if a.cmd == "init":
            print("Đã tạo", CONFIG_PATH, "và", LEARNINGS_PATH)
            return

    if a.cmd == "status":
        cmd_status(cfg)
    elif a.cmd == "connect":
        get_platform(a.platform, {**cfg, "dry_run": False}).connect()
    elif a.cmd == "register":
        v = ops.register(a.meta)
        _print({"slug": v["slug"], "id": v["id"], "title": v["title"]})
    elif a.cmd == "split":
        _print(ops.split(a.slug, cfg))
    elif a.cmd == "queue":
        _print(ops.queue(a.slug, cfg, a.platforms))
    elif a.cmd == "publish-due":
        res = ops.publish_due(cfg)
        if res:
            _print(res)
    elif a.cmd == "reschedule":
        print(ops.reschedule(a.post_id, cfg, a.at))
    elif a.cmd == "cancel":
        from .memory import connect
        with connect() as c:
            c.execute("UPDATE posts SET status='cancelled' WHERE id=? AND status IN ('scheduled','failed')", (a.post_id,))
        print("Đã huỷ bài", a.post_id)
    elif a.cmd == "analytics":
        _print(ops.pull_analytics(cfg))
    elif a.cmd == "comments":
        if a.action == "fetch":
            print(ops.fetch_comments(cfg))
        else:
            if not a.file:
                ap.error("cần file JSON câu trả lời")
            _print(ops.send_replies(a.file, cfg))
    elif a.cmd == "market":
        print(ops.market_scan(cfg, a.queries, days=a.days))
    elif a.cmd == "report":
        if a.kind == "daily":
            notes = Path(a.notes).read_text(encoding="utf-8") if a.notes else ""
            print(report.daily(cfg, notes))
        else:
            print(report.weekly_data())
    elif a.cmd == "strategy":
        if a.key and a.value:
            set_strategy(a.key, a.value, a.reason)
        _print(rows("SELECT * FROM strategy"))
    elif a.cmd == "mode":
        import yaml
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        data["dry_run"] = a.which == "test"
        CONFIG_PATH.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print("Chế độ:", "chạy thử" if data["dry_run"] else "THẬT — sẽ đăng lên kênh")
    elif a.cmd == "install-poster":
        cmd_install_poster()


if __name__ == "__main__":
    main()
