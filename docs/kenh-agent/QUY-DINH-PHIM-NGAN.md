# Quy định của các nền tảng phim ngắn (luật cứng, không được làm sai)

Chủ kênh ghi lại ngày 27/11/2026. Áp dụng cho **mọi** video review/quảng bá dùng tư liệu từ các nền tảng phim ngắn bên dưới.
Nếu một quy định ở đây chặt hơn quy định chung của kênh thì làm theo quy định chặt hơn.
Khi phân vân: chọn cách an toàn hơn, hoặc không đăng.

## A. Luật chung cho tất cả 11 nền tảng

1. **Chỉ dùng tư liệu do chính mình tải xuống từ kho được cấp quyền** của nền tảng đó (thường là các tập miễn phí).
   Cấm dùng tư liệu quảng cáo chính thức, video người khác đã làm, tập trả phí / tập dành cho thành viên / tập chưa mở quyền.
2. **Phải tự biên tập sáng tạo**: lời thuyết minh, phụ đề kể chuyện, cắt ghép lại. Cấm đăng lại nguyên phim
   hoặc chỉ ghép nối các tập gốc. Cấm đăng lại tư liệu chạy quảng cáo.
3. **Bỏ hoàn toàn nhạc nền (BGM) gốc** của phim, thay bằng nhạc được cấp quyền / miễn phí bản quyền.
   (Giữ lời thoại thì phải tách giọng, loại sạch nhạc.)
4. **Không nội dung khêu gợi, phản cảm**, đặc biệt không mở đầu video bằng cảnh khêu gợi.
5. **Không xuyên tạc nội dung gốc**: tiêu đề, mô tả, lời quảng cáo phải đúng với phim, không câu view sai sự thật.
6. Không dùng phông chữ, hình ảnh, nhạc chưa được cấp quyền.
7. Mỗi video chỉ quảng bá **một** nền tảng. Không nhắc tên nền tảng phim khác.
8. Tổng thời lượng video **không vượt quá** tổng thời lượng tư liệu được phép dùng.

## B. Bảng tóm tắt từng nền tảng

| Nền tảng | Hashtag bắt buộc | Link quảng bá | Giới hạn tư liệu | Điểm đặc biệt |
|---|---|---|---|---|
| DramaBox | `#DramaBox` | Có (YouTube cần để vào whitelist) | Tập miễn phí tải được | YouTube whitelist: ≥100 người đăng ký, kênh công khai, video có link/mã quảng bá. FB/TikTok 0 follow vẫn được |
| FlickReels | `#FlickReels` | – | Tư liệu tải được | Tiêu đề cấm "Trọn bộ / Tổng hợp / Full / 全集 / 合集"; cấm hashtag dẫn tới phim trọn bộ; không thông tin nền tảng khác |
| ReelShort | `#ReelShort` | **Bắt buộc** link ReelsLink | Tập miễn phí được cấp quyền | Cấm mở đầu khêu gợi |
| KalosTV | (không bắt buộc) | – | Phim bản địa: chỉ tập trước tập khoá phí. Phim dịch/lồng tiếng: 30% đầu, tối đa 30 tập | Độ giống phim gốc ≤ 70%; 5–10 giây đầu phải có dấu hiệu biên tập rõ; video ≤ 40 phút (bị Kuaikan chặn: ≤ 30 phút); phim bản quyền 番茄/Tomato phải có whitelist riêng, chưa tra được whitelist thì **không làm** và xoá bài cũ; ưu tiên phim bản quyền Qingrong |
| GoodShorts | `#Goodshort` (khuyến nghị — kênh này coi là bắt buộc) | – | Tư liệu lấy được | Facebook: <100 follow chỉ đăng tập miễn phí của phim dịch; ≥100 follow mới đăng ký whitelist để đăng phim sản xuất gốc |
| ShortMAX | **CẤM** hashtag/tên/watermark thương hiệu | – | Chỉ phim trong danh sách ShortMAX phân phối; trong thời lượng được phép của từng phim | Nội dung sáng tạo > 20% thời lượng; 1–2 phút đầu phải có nội dung sáng tạo. **Ngược với các nền tảng khác: không được ghi tên ShortMAX** |
| HoneyReels | `#HoneyReels` | – | Tối đa 30% số tập (100 tập → 30 tập) | Tập trả phí: nội dung sáng tạo > 20%; 1–2 phút đầu có nội dung sáng tạo |
| Dreame | `#Dreameshort` | – | Tư liệu tự tải được | – |
| StarShort | `#StarShort` | – | Tập miễn phí tải được | – |
| PlayLet | `#Playlet` | **Bắt buộc** link PlayLet | Tập miễn phí được cấp quyền | Cấm mở đầu khêu gợi |
| NetShort | `#NetShort` | **Bắt buộc** link NetShort | Tập miễn phí theo API cấp quyền | Video nên ~30 phút, tối đa 40 phút; không ghép nối lặp lại; nội dung tích cực, lành mạnh |

## C. Quy trình kiểm tra trước khi đăng (agent phải làm, ghi vào `tuan_thu`)

Trong `kenh/agent/viec/<slug>.json` ghi thêm `"nen_tang_phim": "<tên nền tảng>"` (ví dụ `"ReelShort"`),
`"link_quang_ba": "..."` nếu nền tảng yêu cầu, và trong `tuan_thu` thêm 3 mục (mỗi mục `{"ok": true, "ghi_chu": "..."}`):

- `pham_vi_tu_lieu`: đã dùng những tập nào, có nằm trong phạm vi được phép không (miễn phí / 30% / danh sách phân phối / whitelist).
- `bo_nhac_goc`: đã loại nhạc nền gốc bằng cách nào, nhạc thay thế lấy từ đâu.
- `bien_tap_sang_tao`: phần thuyết minh/cắt ghép chiếm bao nhiêu %, đoạn mở đầu (5–10 giây / 1–2 phút) có gì.

Lệnh `register` tự kiểm tra và **từ chối** nếu: thiếu các mục trên; thiếu hashtag bắt buộc; ShortMAX mà có tên thương hiệu;
FlickReels mà tiêu đề có chữ "trọn bộ / tổng hợp / full"; thiếu link quảng bá với ReelShort, PlayLet, NetShort;
video dài quá 40 phút với KalosTV, NetShort; nhắc tên nền tảng phim khác.
