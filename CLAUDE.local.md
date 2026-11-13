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
- Ở đầu phiên, nếu `projects/` hoặc `output/` không tồn tại hoặc không phải junction tới Google Drive
  (ví dụ trên máy mới), làm "Cài trên máy mới" bước 3 dưới đây trước khi làm video.
- Không bao giờ xoá nội dung trong `projects/` hoặc `output/` — đó là video của người dùng trên Drive.

## Cài trên máy mới (khi người dùng nhờ)
1. Clone `https://github.com/tahungthe/OpenMontage`, `git remote add upstream https://github.com/OpenMontageInc/OpenMontage.git`.
2. Setup (thay cho `make setup` trên Windows): `python -m venv .venv`; `.venv/Scripts/python.exe -m pip install -r requirements.txt`;
   `cd remotion-composer && npm install`; `pip install piper-tts`; `npx --yes hyperframes --version`; copy `.env.example` → `.env`;
   sau đó `git checkout -- remotion-composer/package-lock.json` nếu npm làm nó thay đổi.
3. Tìm ổ Google Drive (vd `G:\My Drive`). Tạo `OpenMontage\projects` và `OpenMontage\output` trong đó nếu chưa có,
   rồi `cmd /c mklink /J projects "<Drive>\My Drive\OpenMontage\projects"` (tương tự cho `output`).
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
