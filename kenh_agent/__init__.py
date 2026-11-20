"""kenh_agent — bộ công cụ cho agent tự vận hành kênh YouTube / TikTok / Facebook.

Phần "suy nghĩ" (chọn phim, viết kịch bản, trả lời bình luận, phân tích tuần)
do agent Claude `quan-ly-kenh` làm. Gói này lo phần "tay chân" chắc chắn:
bộ nhớ (SQLite), cắt video theo phần, chọn giờ đăng, đăng bài, lấy số liệu,
lấy/gửi bình luận và viết báo cáo.

Chạy: `.venv/Scripts/python.exe -m kenh_agent --help`
"""

__version__ = "0.1.0"
