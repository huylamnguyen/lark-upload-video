# Hướng dẫn dựng "tải video từ máy lên Lark Base" cho khách mới

Người đọc: người triển khai Diginno. Kết quả: máy khách chép video vào một thư mục → video tự lên cột đính kèm của Base khách.

## 0. Hỏi khách trước (5 câu)

1. Tenant Lark **quốc tế (larksuite.com)** hay **Feishu (feishu.cn)**?
2. Link Base + bảng đích. Video gắn vào **dòng có sẵn** (theo mã đơn/mã khách…) hay **mỗi video một dòng mới**?
3. Nếu theo mã: video đặt tên thế nào? Script cần dạng `MÃ_ghi-chú.mp4` (lấy phần trước dấu `_` đầu tiên).
4. Video nặng cỡ nào, mỗi ngày bao nhiêu? (≤ 2 GB/file; dung lượng lưu trữ tenant có hạn — xem Admin > Dung lượng.)
5. Máy chạy là Windows? Có Python chưa? Có cho để App Secret trên máy không (không → dùng §5)?

## 1. Chuẩn bị Base

- Tạo (hoặc chọn) cột kiểu **Tệp đính kèm**, ví dụ `Video`.
- Chế độ `moi-file-mot-dong`: thêm cột Văn bản `Tên file` (dùng để chống tạo dòng trùng khi chạy lại).
- Chế độ `theo-ma`: cột mã (Văn bản) phải **duy nhất** — trùng mã script sẽ từ chối, không đoán.
- Lấy token: link `https://<tenant>.larksuite.com/base/<BASE_TOKEN>?table=<TABLE_ID>&view=…`. Base nằm trong Wiki thì link là `/wiki/<node>` — phải đổi ra base token thật (`lark-cli wiki spaces get_node --params '{"token":"<node>"}'` → `obj_token`).

## 2. Tạo app Lark riêng cho khách (khuyên: 1 khách = 1 app)

Developer Console (`open.larksuite.com/app`) > Create custom app > tên "Diginno Upload – <Khách>".
- **Permissions & Scopes** (tenant token): `bitable:app` (đọc/ghi Base). Nếu upload báo `99991672` đòi scope, thêm `drive:file:upload` (hoặc đúng scope trong câu báo lỗi).
- **Bật Bot** (Features > Bot) để có thể mời app vào Base.
- **Version Management > Create version > Publish.** Mỗi lần thêm scope phải phát hành lại; admin tenant khách có thể phải duyệt.
- Lấy App ID + App Secret (Credentials).

Vì sao app riêng: app chỉ đọc/ghi được những Base đã mời nó. Lộ secret thì thiệt hại gói trong đúng Base đó; thu hồi bằng Reset secret — không đụng khách khác.

## 3. Mời app vào Base

Base > `…` (góc phải) > **Thêm ứng dụng / Add app** > chọn app > quyền **Có thể chỉnh sửa**.
Chưa làm bước này: đọc được lỗi `91403`/`1254302`, ghi lỗi `1254045 FieldNameNotFound` (dễ tưởng sai tên cột).
Base bật **Quyền nâng cao**: thêm app vào một vai trò có quyền sửa bảng đích.

## 4. Cài lên máy khách

Gói gửi khách = `lark_upload.py` + `.env` đã điền (từ `templates/cau-hinh.mau.env`).
Không gửi `.env` qua chat nhóm — tải lên Lark Drive chia sẻ riêng người phụ trách, hoặc để AI agent trên máy khách tự tạo `.env` từ giá trị bạn đọc qua điện thoại/Lark riêng.

Máy khách: Python 3.9+ (không cần pip). Rồi đưa `templates/prompt-may-khach.md` cho AI agent trên máy đó (agent tự hỏi link Base, App ID, tên cột, thư mục).

Nghiệm thu, theo thứ tự:
1. `python lark_upload.py --kiem-tra` → 3 dấu ✓.
2. `python lark_upload.py --dry` → đúng danh sách file, đúng dòng đích.
3. Gửi 1 video < 20 MB, mở Base xem phát được.
4. Gửi 1 video > 20 MB (thấy dòng "mảnh 1/N…").
5. Chạy lại lần nữa cùng file (chép lại từ `da-gui`) → phải báo **đã có**, không tạo dòng/file trùng.

## 5. Không để App Secret trên máy khách

Dựng trạm cấp token n8n — xem `mau-tram-n8n.md` mẫu 1. Máy khách đặt `TOKEN_URL` + `TOKEN_KEY`, bỏ APP_ID/SECRET. Chỉ token đi qua n8n, video không qua.

## 6. Chạy tự động (tuỳ chọn)

Task Scheduler, mỗi 15 phút:
```
schtasks /Create /TN "Diginno - Gui video len Lark" /SC MINUTE /MO 15 /TR "\"<python.exe>\" \"<thư mục>\lark_upload.py\"" /F
```
Script tự bỏ qua file vừa sửa < 60 giây (đang chép) và có khoá `.dang-chay.lock` chống hai lượt chồng nhau (khoá cũ > 6 giờ coi như hết hiệu lực).

## 7. Đọc lỗi

| Thấy | Nghĩa | Làm |
|---|---|---|
| `LẤY TOKEN HỎNG code=10003/10014` | Sai App ID/Secret | Chép lại từ Credentials |
| `99991672 … scopes` | Thiếu scope | Thêm scope trong câu lỗi → phát hành lại app |
| `91403`, `1254302`, `1254045` | App chưa được mời / không có quyền sửa | §3 |
| `không có dòng nào Mã = …` | Tên file sai mã hoặc dòng chưa tạo | Sửa tên file |
| `N dòng trùng Mã` | Mã không duy nhất | Khách dọn Base |
| `MẤT n FILE CŨ` | Ghi đè mất file (chưa từng gặp) | Dừng, xem lịch sử dòng trong Base để khôi phục |
| `99991403` | Hết hạn mức tải lên / dung lượng tenant | Admin tenant khách |
| Mạng / 5xx | Tự thử lại 4 lần (2/5/15/30 s) | Chạy lại; file chưa gửi vẫn nằm nguyên |

Nhật ký từng file: `nhat-ky-upload.jsonl` (1 dòng JSON/lượt: file, MB, record_id, file_token, giây, lỗi).
