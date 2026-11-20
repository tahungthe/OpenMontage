"""Bộ nhớ lâu dài của agent (SQLite tại kenh/agent/bo-nho.db).

Lưu mọi thứ agent cần để học theo thời gian: video đã làm, bài đã đăng,
số liệu theo từng lần đo, bình luận đã trả lời, kết quả nghiên cứu thị trường,
và các "chiến lược" (giờ đăng, định dạng Facebook...) đang áp dụng.
Bài học bằng chữ nằm riêng ở kenh/agent/bai-hoc.md để agent đọc/ghi.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from .config import DB_PATH, VN_TZ, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    film TEXT,
    full_path TEXT,
    description TEXT,
    tags TEXT,               -- JSON list
    thumbnail_path TEXT,
    status TEXT DEFAULT 'ready',   -- ready | queued | published | archived
    created_at TEXT NOT NULL,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES videos(id),
    idx INTEGER NOT NULL,
    total INTEGER NOT NULL,
    path TEXT NOT NULL,
    start_s REAL, end_s REAL,
    hook TEXT,
    UNIQUE(video_id, idx)
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES videos(id),
    part_idx INTEGER,                -- NULL = bản full
    platform TEXT NOT NULL,          -- youtube | tiktok | facebook
    format TEXT NOT NULL,            -- full | phan | reel
    file_path TEXT NOT NULL,
    title TEXT, caption TEXT,
    scheduled_at TEXT NOT NULL,      -- ISO, giờ VN
    status TEXT DEFAULT 'scheduled', -- scheduled | posting | posted | failed | cancelled
    remote_id TEXT, url TEXT,
    posted_at TEXT, error TEXT, attempts INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    captured_at TEXT NOT NULL,
    hours_since_post REAL,
    views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER,
    avg_view_pct REAL, avg_view_s REAL, watch_time_min REAL, subs_gained INTEGER,
    raw TEXT
);
CREATE TABLE IF NOT EXISTS channel_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    followers INTEGER, total_views INTEGER, video_count INTEGER, raw TEXT
);
CREATE TABLE IF NOT EXISTS comments (
    platform TEXT NOT NULL,
    remote_id TEXT NOT NULL,
    post_id INTEGER,
    remote_video_id TEXT,
    author TEXT, text TEXT, like_count INTEGER,
    created_at TEXT,
    status TEXT DEFAULT 'new',       -- new | replied | skipped
    reply_text TEXT, replied_at TEXT, reply_remote_id TEXT,
    PRIMARY KEY (platform, remote_id)
);
CREATE TABLE IF NOT EXISTS research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    source TEXT, url TEXT UNIQUE, title TEXT, channel TEXT, film TEXT,
    views INTEGER, likes INTEGER, comments INTEGER,
    published_at TEXT, duration_s INTEGER, channel_subs INTEGER,
    views_per_day REAL, outlier_score REAL, notes TEXT
);
CREATE TABLE IF NOT EXISTS strategy (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL, kind TEXT NOT NULL, message TEXT, data TEXT
);
"""


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)
    return dt.astimezone(VN_TZ).isoformat(timespec="seconds")


def parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)
    return dt.astimezone(VN_TZ)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_event(kind: str, message: str, data: Any = None) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO events(at, kind, message, data) VALUES (?,?,?,?)",
            (iso(now_vn()), kind, message, json.dumps(data, ensure_ascii=False) if data is not None else None),
        )


def get_strategy(key: str, default: str | None = None) -> str | None:
    with connect() as c:
        row = c.execute("SELECT value FROM strategy WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_strategy(key: str, value: str, reason: str = "") -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO strategy(key, value, updated_at, reason) VALUES (?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, reason=excluded.reason",
            (key, value, iso(now_vn()), reason),
        )
    log_event("strategy", f"{key} = {value}", {"reason": reason})


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]
