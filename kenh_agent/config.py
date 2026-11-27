"""Đường dẫn, cấu hình và bí mật của agent kênh.

Dữ liệu riêng của người dùng nằm trong `kenh/agent/` (không đưa lên GitHub).
Bí mật (token, mật khẩu ứng dụng) nằm trong `.env` hoặc `kenh/agent/bi-mat/`.
"""

from __future__ import annotations

import copy
import os
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
KENH_DIR = REPO_ROOT / "kenh"
# KENH_AGENT_DIR cho phép chạy thử với một bộ nhớ riêng, không đụng dữ liệu thật
AGENT_DIR = Path(os.environ["KENH_AGENT_DIR"]) if os.environ.get("KENH_AGENT_DIR") else KENH_DIR / "agent"
SECRETS_DIR = AGENT_DIR / "bi-mat"
REPORTS_DIR = AGENT_DIR / "bao-cao"
WORK_DIR = AGENT_DIR / "viec"          # file trao đổi giữa CLI và agent Claude
SOURCE_FILMS_DIR = KENH_DIR / "phim-nguon"
CONFIG_PATH = AGENT_DIR / "cau-hinh.yaml"
LEARNINGS_PATH = AGENT_DIR / "bai-hoc.md"
DB_PATH = AGENT_DIR / "bo-nho.db"

# Giờ Việt Nam
VN_TZ = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")

load_dotenv(REPO_ROOT / ".env")

DEFAULT_CONFIG: dict[str, Any] = {
    # Khi true: không gọi API thật, chỉ giả lập và ghi log. Tự tắt khi bạn đã kết nối tài khoản.
    "dry_run": True,
    "kenh": {
        "ten": "Kênh review phim",
        "ngach": "review / tóm tắt phim tiếng Việt",
        "giong_tra_loi": "thân thiện, hài hước nhẹ, xưng 'mình' gọi 'bạn', như admin kênh",
        "hashtag_mac_dinh": ["#reviewphim", "#tomtatphim", "#phimhay"],
    },
    # Tiếp thị liên kết phim ngắn (docs/kenh-agent/QUY-DINH-PHIM-NGAN.md)
    "phim_ngan": {
        "app_dang_lam": "ShortMAX",      # giai đoạn đầu chỉ làm 1 app
        "ngon_ngu": "en",                # thuyết minh đúng ngôn ngữ gốc của phim
        "kenh_youtube_id": "",           # ID kênh đã báo cáo (报备) với bên phân phối; trống = không đăng
    },
    "nhip_dang": {
        "youtube_full_moi_tuan": 5,      # số video full/tuần trên YouTube
        "tiktok_phan_moi_ngay": 3,       # số phần cắt/ngày trên TikTok
        "facebook_bai_moi_ngay": 2,
        "khoang_cach_toi_thieu_phut": 150,  # giữa 2 bài cùng nền tảng
    },
    "cat_phan": {
        "do_dai_muc_tieu_giay": 150,     # mỗi phần TikTok ~2,5 phút
        "do_dai_toi_thieu_giay": 60,
        "do_dai_toi_da_giay": 300,
        "phu_de_phan": "Phần {n}/{tong}",
    },
    # Giờ vàng mặc định cho khán giả Việt Nam; agent sẽ tự học và điều chỉnh.
    "gio_vang": {
        "youtube": [11, 12, 19, 20, 21],
        "tiktok": [7, 11, 12, 18, 20, 21, 22],
        "facebook": [8, 12, 19, 20, 21],
    },
    "kham_pha_gio_moi": 0.2,             # 20% lần chọn thử giờ khác để học thêm
    # Facebook: agent thử cả hai kiểu, rồi theo số liệu mà chọn
    "facebook_dinh_dang": "thu-nghiem",  # thu-nghiem | full | phan
    "tiktok_che_do": "direct",           # direct (đăng thẳng) | inbox (gửi bản nháp vào app)
    "tiktok_quyen_rieng_tu": "PUBLIC_TO_EVERYONE",
    "youtube_quyen_rieng_tu": "public",
    "youtube_danh_muc": "1",             # 1 = Film & Animation
    "binh_luan": {
        "tra_loi_toi_da_moi_lan": 40,
        "bo_qua_spam": True,
    },
    "ngan_sach": {
        "usd_moi_ngay": 3.0,             # trần chi phí OpenMontage mỗi ngày
        "usd_moi_video": 2.0,
        "uu_tien_mien_phi": True,
    },
    "bao_cao": {
        "telegram": False,               # bật nếu đã điền TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trong .env
    },
}


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_dirs() -> None:
    for d in (AGENT_DIR, SECRETS_DIR, REPORTS_DIR, WORK_DIR, SOURCE_FILMS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            "# Cấu hình agent quản lý kênh. Sửa giá trị rồi lưu là xong.\n"
            + yaml.safe_dump(DEFAULT_CONFIG, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    user = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    cfg = _deep_merge(DEFAULT_CONFIG, user)
    if os.environ.get("KENH_DRY_RUN") in ("1", "true", "yes"):
        cfg["dry_run"] = True
    return cfg


def env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name, default)
    return val.strip() if isinstance(val, str) else val
