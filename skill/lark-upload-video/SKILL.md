---
name: lark-upload-video
description: Tải file từ máy local (video, ảnh, PDF, file nặng tới 2 GB) lên cột Tệp đính kèm của Lark Base — script Python không cần cài thêm gì, tự cắt mảnh file >20 MB, ghi thêm (không đè) file cũ, đọc lại xác nhận, chống gửi trùng, chuyển file đã gửi sang thư mục da-gui. Kèm hướng dẫn dựng cho khách mới (app Lark, quyền, base khác), prompt giao cho AI agent trên máy khách, và mẫu trạm n8n. Dùng khi user nói "up/tải/đẩy file/video từ máy lên Lark", "upload video lên base", "gắn file vào bản ghi", "đồng bộ thư mục lên Lark", "upload_all", "upload_prepare", "cắt mảnh", "file quá 20MB", "cài cho máy khách tự đẩy file".
---

# Tải file/video local lên Lark Base

Repo công khai: https://github.com/huylamnguyen/lark-upload-video

## Chọn đường nào

| Tình huống | Đường |
|---|---|
| **Video / file lớn tới 2 GB**, máy khách chạy script | **A. `scripts/lark_upload.py`** gọi thẳng Lark bằng app riêng của khách (mặc định) |
| Như A nhưng không để App Secret trên máy | **A + trạm cấp token n8n** — `references/mau-tram-n8n.md` mẫu 1 |
| File ≤ 10 MB, máy khách không được giữ token nào | **Trạm nhận file n8n** — mẫu 2. Không dùng cho video |
| Người triển khai tự đẩy từ máy có `lark-cli` | `lark-cli base +record-upload-attachment --base-token … --table-id … --record-id … --field-id "Video" --file a.mp4` (tự cắt mảnh, ≤ 2 GB) |

## Cơ chế (chạy thật 30/09/2026 — 27 MB cắt 7 mảnh, tải về khớp SHA-256)

1. `POST /auth/v3/tenant_access_token/internal` (app_id + app_secret), hoặc xin token từ `TOKEN_URL`.
2. Tải vào kho của base: `parent_type=bitable_file`, `parent_node=<base token>`.
   - ≤ 20 MB: `POST /drive/v1/medias/upload_all` (multipart: file_name, parent_type, parent_node, size, file).
   - \> 20 MB: `upload_prepare` → `upload_id`, `block_size` (4 MB), `block_num` → `upload_part` từng mảnh (upload_id, seq, size, checksum adler32, file) → `upload_finish` → `file_token`.
3. Đọc ô đính kèm → `PUT records/{id}` với **cũ + mới** → đọc lại: có token mới, không mất token cũ. **Không bao giờ PUT chỉ file mới** — làm vậy là xoá file cũ.
4. Đọc lại OK mới chuyển file sang `da-gui/`.

## Làm cho khách mới

1. `references/huong-dan-su-dung.md` — tạo app riêng, scope, mời app vào base, nghiệm thu.
2. Đưa `templates/prompt-may-khach.md` cho AI agent trên máy khách (không cần điền trước; agent tự hỏi). Script được tải từ raw GitHub của repo trên.
3. Nghiệm thu: `--kiem-tra` → `--dry` → 1 file nhỏ → 1 video > 20 MB → chạy lại cùng file phải báo "đã có".

## Lệnh

```
python lark_upload.py --kiem-tra        # token + cột + kiểu cột, không ghi
python lark_upload.py --dry             # liệt kê, không gửi
python lark_upload.py                   # gửi cả THU_MUC_NGUON
python lark_upload.py "D:\video\a.mp4" --record-id recXXXX
```
Cấu hình trong `.env` cạnh script (`templates/cau-hinh.mau.env`). `LARK_BASE_LINK` = link bảng dán từ trình duyệt, script tự tách base token + table id (link Wiki cần scope `wiki:wiki:readonly`). Nhật ký: `nhat-ky-upload.jsonl`. Mã thoát 0 = không lỗi.

## Bẫy đã gặp

- `1254045 FieldNameNotFound` khi ghi thường là **app chưa có quyền sửa base**, không phải sai tên cột. `91403`/`1254302` = chưa mời app vào base.
- `99991672 … scopes` = thiếu scope; thêm xong **phải phát hành lại app**.
- Base bật quyền nâng cao có thể đòi `LARK_EXTRA={"bitablePerm":{"tableId":"tbl…","rev":1}}` (chưa kiểm).
- Tenant Feishu: `LARK_DOMAIN=https://open.feishu.cn`.
- Webhook n8n gãy ở ~12–16 MB → đừng cho video đi qua n8n.
- Chưa kiểm: Lark xem trước mọi codec video không (MP4 H.264 an toàn nhất).
