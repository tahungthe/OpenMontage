# Ghi chú riêng của máy này (không đưa lên GitHub)

## Người dùng
- Người dùng KHÔNG biết lập trình. Luôn trả lời bằng tiếng Việt, giải thích đơn giản, không bắt họ gõ lệnh.
- Mọi thao tác Git/cài đặt: Claude tự làm, chỉ hỏi khi cần người dùng quyết định hoặc đăng nhập.

## Nguồn code
- `origin`   = fork của người dùng: https://github.com/tahungthe/OpenMontage
- `upstream` = bản gốc của tác giả: https://github.com/OpenMontageInc/OpenMontage
- Nhánh chính: `main`. Môi trường Python: `.venv` (Windows: `.venv/Scripts/python.exe`).

## Video lưu trên Google Drive
- `projects/` và `output/` trong repo là **junction** (lối tắt thư mục) trỏ tới
  `<Google Drive>\My Drive\OpenMontage\projects` và `...\output`, để máy nào cũng thấy video.
- Ở đầu phiên, nếu `projects/`, `output/` hoặc `kenh/` không tồn tại hoặc không phải junction tới Google Drive
  (ví dụ trên máy mới), làm "Cài trên máy mới" bước 3 dưới đây trước khi làm video.
- Không bao giờ xoá nội dung trong `projects/` hoặc `output/` — đó là video của người dùng trên Drive.

## Tìm chủ đề video (agent `nghien-cuu-chu-de`)
- `kenh/` là junction tới `<Google Drive>\My Drive\OpenMontage\kenh` (hồ sơ kênh, lịch sử chủ đề, báo cáo nghiên cứu).
  Nội dung trong đó là thông tin riêng của người dùng: không đưa lên GitHub.
- Khi người dùng muốn gợi ý/tìm chủ đề video (vd "gợi ý chủ đề", "tuần này làm video gì"):
  1. Nếu chưa có `kenh/ho-so-kenh.md`: hỏi người dùng tối đa 5 câu ngắn, từng ít một, kèm ví dụ để họ chọn
     (ngách; nền tảng; khán giả; mục tiêu; phong cách & giới hạn: lộ mặt hay không, ngân sách, số video/tuần, độ dài).
     Ghi lại thành `kenh/ho-so-kenh.md`. Hồ sơ có sẵn thì không hỏi lại; người dùng muốn đổi thì sửa file.
  2. Gọi agent `nghien-cuu-chu-de` (Agent tool), truyền yêu cầu cụ thể của người dùng. Việc này mất vài phút: báo người dùng.
  3. Trình bày Top 3 ngắn gọn, dễ hiểu, hỏi người dùng muốn làm video nào trước.
  4. Khi người dùng chọn: đổi trạng thái trong `kenh/lich-su-chu-de.md` thành "đã làm" (hoặc "bỏ qua" nếu họ từ chối),
     rồi bắt đầu sản xuất theo AGENT_GUIDE.md, dùng phần Top 5 của báo cáo làm brief.

## Cài trên máy mới (khi người dùng nhờ)
1. Clone `https://github.com/tahungthe/OpenMontage`, `git remote add upstream https://github.com/OpenMontageInc/OpenMontage.git`.
2. Setup (thay cho `make setup` trên Windows): `python -m venv .venv`; `.venv/Scripts/python.exe -m pip install -r requirements.txt`;
   `cd remotion-composer && npm install`; `pip install piper-tts`; `npx --yes hyperframes --version`; copy `.env.example` → `.env`;
   sau đó `git checkout -- remotion-composer/package-lock.json` nếu npm làm nó thay đổi.
3. Tìm ổ Google Drive (vd `G:\My Drive`). Tạo `OpenMontage\projects` và `OpenMontage\output` trong đó nếu chưa có,
   rồi `cmd /c mklink /J projects "<Drive>\My Drive\OpenMontage\projects"` (tương tự cho `output` và `kenh`).
   Thêm dòng `kenh/` và `kenh` vào `.git/info/exclude` để `kenh` không bị đưa lên GitHub.
   Nếu máy chưa cài Google Drive for desktop, nhờ người dùng cài và đăng nhập trước.
4. API key (`.env`) KHÔNG có trên GitHub (fork là công khai). Nhắc người dùng chép key sang, không bao giờ commit `.env`.

## Nhắc cập nhật (làm ở đầu mỗi phiên)
Ở câu trả lời đầu tiên của mỗi phiên, chạy `git fetch upstream --quiet` rồi
`git rev-list --count main..upstream/main`. Nếu số > 0, nhắc người dùng một dòng:
"OpenMontage có N thay đổi mới từ tác giả. Muốn cập nhật thì bạn chỉ cần nói: **cập nhật OpenMontage**."
Nếu không có mạng hoặc lệnh lỗi thì bỏ qua, không làm phiền người dùng.

## Khi người dùng nói "cập nhật OpenMontage"
1. Không cập nhật khi đang dở một video; nếu đang dở thì hỏi trước.
2. `git status` — nếu có file người dùng đã sửa, báo cho họ và giữ lại (commit hoặc stash), không xoá.
3. `git pull upstream main` (gộp bản mới của tác giả). Nếu xung đột, tự giải quyết và giải thích ngắn gọn.
4. Nếu `requirements.txt` đổi: `.venv/Scripts/python.exe -m pip install -r requirements.txt`.
   Nếu `remotion-composer/package.json` đổi: `cd remotion-composer && npm install`.
5. `git push origin main` để fork trên GitHub cũng mới. Nếu cần đăng nhập GitHub, nhờ người dùng đăng nhập trong cửa sổ hiện ra.
6. Báo lại bằng 2-3 câu: đã cập nhật gì, có gì cần chú ý.
