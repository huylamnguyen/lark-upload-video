# Prompt cài trên máy khách

Chép **toàn bộ khối dưới đây** dán cho AI agent (Claude Code, Codex, Cursor…) trên máy Windows của khách. Không cần sửa gì: agent tự hỏi người ngồi máy những thông tin còn thiếu.

Người triển khai chỉ cần chuẩn bị trước cho khách (xem README của repo https://github.com/huylamnguyen/lark-upload-video mục 2–3): **App ID**, **App Secret** (gửi riêng), app đã được **mời vào Base với quyền chỉnh sửa**, và Base có một cột kiểu **Tệp đính kèm**.

---

```text
Bạn là kỹ thuật viên cài đặt trên máy Windows này. Việc cần làm: cài một script để video
(hoặc file bất kỳ) trong một thư mục tự tải lên cột Tệp đính kèm của Lark Base.
Làm đúng thứ tự, sau mỗi bước báo kết quả ngắn bằng tiếng Việt. KHÔNG sửa script.
Gặp lỗi không có trong bảng cuối thì dừng lại, chép nguyên văn lỗi cho người dùng.

BƯỚC 1 — Hỏi người dùng 5 thông tin (hỏi một lượt, chờ trả lời đủ):
  a) Link Base: mở đúng BẢNG cần gắn video trên trình duyệt, copy nguyên thanh địa chỉ
     (phải có "?table=tbl...").
  b) App ID (dạng cli_...) do bên triển khai cấp.
  c) Tên cột Tệp đính kèm nhận video (ví dụ: Video).
  d) Cách gắn: (1) mỗi video tạo một dòng mới, hay (2) gắn vào dòng có sẵn theo mã —
     khi đó video phải đặt tên "MÃ_ghi-chú.mp4" và cho biết tên cột chứa mã.
     Với cách (1), hỏi tên cột văn bản để ghi tên file (mặc định "Tên file").
  e) Thư mục trên máy sẽ chứa video cần gửi (ví dụ D:\Video can gui).
  TUYỆT ĐỐI KHÔNG hỏi App Secret trong chat.

BƯỚC 2 — Python: chạy `python --version`, cần 3.9 trở lên. Chưa có thì
  `winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements`,
  mở cửa sổ lệnh mới rồi kiểm lại. Không cần pip install gì.

BƯỚC 3 — Tải script (PowerShell):
  New-Item -ItemType Directory -Force C:\LarkUpload | Out-Null
  Invoke-WebRequest -UseBasicParsing -OutFile C:\LarkUpload\lark_upload.py `
    https://raw.githubusercontent.com/huylamnguyen/lark-upload-video/main/skill/lark-upload-video/scripts/lark_upload.py
  Kiểm: file tồn tại, dòng đầu là "#!/usr/bin/env python3". Tạo thư mục ở câu (e) nếu chưa có.

BƯỚC 4 — Tạo C:\LarkUpload\.env (UTF-8, không BOM cũng được) với nội dung, thay <...> bằng câu trả lời:
  LARK_APP_ID=<b>
  LARK_APP_SECRET=
  LARK_BASE_LINK=<a>
  COT_FILE=<c>
  CHE_DO_GHEP=<moi-file-mot-dong nếu chọn (1), theo-ma nếu chọn (2)>
  COT_TEN=<tên cột ghi tên file, cách (1)>
  COT_MA=<tên cột mã, cách (2)>
  THU_MUC_NGUON=<e>
  THU_MUC_DA_GUI_TEN=da-gui
  CHUYEN_SAU_KHI_GUI=1
  (Tenant Feishu Trung Quốc — link có feishu.cn — thêm dòng LARK_DOMAIN=https://open.feishu.cn)
  Rồi nói người dùng: "Mở C:\LarkUpload\.env bằng Notepad, dán App Secret vào ngay sau
  LARK_APP_SECRET= , lưu lại rồi báo tôi." Khi người dùng báo xong, chỉ kiểm dòng đó
  KHÔNG RỖNG (in độ dài), không bao giờ in giá trị secret.

BƯỚC 5 — Kiểm tra, không ghi gì:
  cd C:\LarkUpload ; python lark_upload.py --kiem-tra
  Đạt khi có "Lấy token ... OK" và dấu ✓ cho các cột.

BƯỚC 6 — Chạy thử: nhờ người dùng chép 1 video ngắn vào thư mục (e) (cách (2) thì đặt tên
  đúng MÃ_ghi-chú.mp4), chờ 1 phút, chạy `python lark_upload.py --dry`. Đọc danh sách cho
  người dùng xác nhận.

BƯỚC 7 — Gửi thật: `python lark_upload.py`. Đạt khi báo "đã gửi" và file đã chuyển vào
  thư mục con "da-gui". Nhờ người dùng mở Base xem video nằm đúng dòng và phát được.

BƯỚC 8 — Hỏi người dùng có muốn tự chạy mỗi 15 phút không. Có thì (PowerShell):
  $py = (python -c "import sys;print(sys.executable)")
  schtasks /Create /TN "Lark - Gui video" /SC MINUTE /MO 15 /TR "`"$py`" `"C:\LarkUpload\lark_upload.py`"" /F
  Kiểm: schtasks /Query /TN "Lark - Gui video"

BƯỚC 9 — Báo cáo: phiên bản Python, thư mục cài, kết quả bước 5–7 (record_id của file thử),
  đã tạo lịch chạy chưa. Không kèm secret.

BẢNG LỖI:
  "LẤY TOKEN HỎNG"                          -> App ID/Secret sai hoặc thừa dấu cách: nhờ dán lại.
  99991672 / 91403 / 1254302 / 1254045      -> app chưa đủ quyền hoặc chưa được mời vào Base với
                                               quyền chỉnh sửa: dừng, báo bên triển khai kèm lỗi.
  "Link Wiki: không đổi được ra base token" -> mở Base ra tab riêng, lấy link dạng /base/... dán lại.
  "KHÔNG CÓ cột ..."                        -> hỏi lại đúng tên cột (phân biệt hoa thường, dấu).
  "không có dòng nào Mã = ..."              -> tên video sai mã: đổi tên rồi chạy lại.
  Lỗi mạng                                  -> kiểm internet, chạy lại; video chưa gửi vẫn nằm nguyên.
```
