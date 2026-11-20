# Agent quản lý kênh — Hướng dẫn cho chủ kênh

Agent `quan-ly-kenh` tự vận hành kênh review phim trên YouTube, TikTok và Facebook:
nghiên cứu phim đang hot → làm video bằng OpenMontage → cắt phần cho TikTok → chọn giờ đăng →
trả lời bình luận → lấy số liệu → báo cáo hằng ngày → phân tích hằng tuần và tự rút kinh nghiệm.

Bạn chỉ cần làm **một lần**: kết nối 3 tài khoản (dưới đây). Phần còn lại agent tự làm.
Khi chưa kết nối, agent chạy ở **chế độ thử**: vẫn làm video, xếp lịch, viết báo cáo, nhưng không đăng thật.

## Lịch làm việc tự động

| Khi nào | Việc | Ai chạy |
|---|---|---|
| 15 phút/lần | Đăng các bài đã tới giờ | Windows Task Scheduler (`KenhAgent-DangBai`), không tốn AI |
| 7:00 mỗi ngày | Số liệu, bình luận, làm video mới, xếp lịch, báo cáo ngày | Tác vụ hẹn giờ trong app Claude |
| 21:30 mỗi ngày | Trả lời bình luận buổi tối | Tác vụ hẹn giờ trong app Claude |
| 8:00 thứ Hai | Phân tích tuần, cập nhật bài học, kế hoạch tuần tới | Tác vụ hẹn giờ trong app Claude |

Tác vụ hẹn giờ chỉ chạy khi app Claude đang mở (máy tắt thì chạy bù khi mở lại).

Báo cáo nằm ở `kenh/agent/bao-cao/`. Muốn nhận trên điện thoại: xem mục Telegram cuối trang.

## Kết nối YouTube (khoảng 10 phút)

1. Vào https://console.cloud.google.com → tạo dự án mới (tên tuỳ ý).
2. Mục **APIs & Services → Library**: bật **YouTube Data API v3** và **YouTube Analytics API**.
3. Mục **OAuth consent screen**: chọn External, điền tên app, email; thêm email của bạn vào **Test users**.
   (Sau đó bấm **Publish app** để token không hết hạn sau 7 ngày.)
4. Mục **Credentials → Create credentials → OAuth client ID → Desktop app** → tải file JSON.
5. Đổi tên file thành `youtube-client.json`, chép vào `kenh/agent/bi-mat/`.
6. Nói với Claude: **"kết nối YouTube"** → trình duyệt mở ra, bạn đăng nhập tài khoản kênh và bấm Cho phép.

Lưu ý: YouTube cho mỗi dự án ~6 lượt tải video/ngày với hạn mức mặc định — đủ cho nhịp đăng của kênh.

## Kết nối Facebook Page

1. Vào https://developers.facebook.com → **My Apps → Create App** (loại Business).
2. Mở **Graph API Explorer**, chọn app vừa tạo, chọn Page của bạn, tích các quyền:
   `pages_show_list, pages_manage_posts, pages_read_engagement, pages_manage_engagement, pages_read_user_content, read_insights`.
3. Bấm **Generate Access Token**, rồi dùng **Access Token Debugger → Extend** để lấy token dài hạn của Page.
4. Mở file `.env` trong thư mục OpenMontage, thêm 2 dòng:
   ```
   FB_PAGE_ID=số-id-của-page
   FB_PAGE_TOKEN=token-dài-hạn
   ```
   (hoặc nhờ Claude: "mở file .env để mình dán token Facebook" — bạn tự dán, Claude không cần thấy token.)

## Kết nối TikTok

1. Vào https://developers.tiktok.com → tạo app → thêm **Login Kit** và **Content Posting API** (bật Direct Post).
2. Scope: `user.info.basic, user.info.stats, video.list, video.upload, video.publish`.
3. Redirect URI: `http://localhost:8765/callback/`
4. Thêm vào `.env`:
   ```
   TIKTOK_CLIENT_KEY=...
   TIKTOK_CLIENT_SECRET=...
   ```
5. Nói với Claude: **"kết nối TikTok"** → đăng nhập và cho phép.

Giới hạn của TikTok:
- App **chưa được TikTok duyệt** chỉ đăng được video ở chế độ riêng tư. Trong lúc chờ duyệt, đặt
  `tiktok_che_do: inbox` trong `kenh/agent/cau-hinh.yaml`: video sẽ vào mục thông báo/bản nháp trong app TikTok,
  bạn chỉ cần bấm Đăng. Gửi app đi duyệt ở mục **App review** trên trang nhà phát triển.
- TikTok không mở API bình luận cho tài khoản thường → bình luận TikTok bạn xem trong app.

## Bật chế độ thật

Khi đã kết nối xong, nói với Claude: **"bật chế độ thật cho agent kênh"**
(tương đương `.venv/Scripts/python.exe -m kenh_agent mode live`).

## Nhận báo cáo qua Telegram (tuỳ chọn)

1. Trong Telegram, nhắn @BotFather → `/newbot` → lấy token.
2. Nhắn một tin bất kỳ cho bot vừa tạo, rồi mở `https://api.telegram.org/bot<token>/getUpdates` để lấy `chat.id`.
3. Thêm vào `.env`: `TELEGRAM_BOT_TOKEN=...` và `TELEGRAM_CHAT_ID=...`
4. Trong `kenh/agent/cau-hinh.yaml` đặt `bao_cao: telegram: true`.

## Bản quyền — điều quan trọng nhất

Kênh review phim dễ bị Content ID / gậy bản quyền. Agent được dặn:
- không bao giờ đăng lại phim gốc, chỉ dùng đoạn ngắn kèm lời bình;
- không tải phim lậu, không tải video của kênh khác;
- nguồn hình ưu tiên: phim bạn để trong `kenh/phim-nguon/<ten-phim>/` (bạn chịu trách nhiệm quyền dùng),
  phim phạm vi công cộng, hoặc kể chuyện bằng hình AI tự tạo.

Nếu kênh nhận claim/gậy, agent sẽ báo trong báo cáo ngày và tránh nguồn đó về sau.

## Các thư mục

| Thư mục | Nội dung |
|---|---|
| `kenh/agent/bao-cao/` | Báo cáo ngày, báo cáo tuần |
| `kenh/agent/bai-hoc.md` | Những gì agent đã học được về kênh |
| `kenh/agent/cau-hinh.yaml` | Nhịp đăng, giờ vàng, ngân sách |
| `kenh/agent/video/` | Video đã ghi nhận và các phần đã cắt |
| `kenh/agent/bi-mat/` | Token đăng nhập (không chia sẻ, không đưa lên GitHub) |
| `kenh/phim-nguon/` | Bạn bỏ phim nguồn vào đây (nếu có) |
