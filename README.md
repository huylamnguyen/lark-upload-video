# lark-upload-video

Tải video (và file bất kỳ tới 2 GB) từ máy Windows/Mac/Linux lên **cột Tệp đính kèm của Lark Base**. Một file Python, chỉ dùng thư viện chuẩn, không cần `pip install`.

- File ≤ 20 MB tải một lần; lớn hơn tự **cắt mảnh 4 MB** (`upload_prepare → upload_part → upload_finish`).
- **Ghi thêm, không đè**: đọc file cũ trên ô → ghi cũ + mới → đọc lại xác nhận không mất file nào.
- **Không gửi trùng**: file cùng tên + cùng dung lượng đã có trên dòng thì bỏ qua.
- Gửi xong mới chuyển file sang thư mục `da-gui`; mạng rớt giữa chừng thì file vẫn ở chỗ cũ, chạy lại là tiếp.
- Bỏ qua file vừa sửa < 60 giây (đang chép vào), có khoá chống hai lượt chạy chồng nhau, nhật ký `nhat-ky-upload.jsonl`.

Đã thử thật: video 27 MB cắt 7 mảnh, tải về so SHA-256 khớp từng byte.

| Tài liệu | Dành cho |
|---|---|
| [PROMPT-MAY-KHACH.md](PROMPT-MAY-KHACH.md) | Dán cho AI agent trên máy khách, tự cài từ đầu đến cuối |
| [skill/lark-upload-video/](skill/lark-upload-video/) | Claude Code skill — chép vào `~/.claude/skills/` |
| [Hướng dẫn chi tiết](skill/lark-upload-video/references/huong-dan-su-dung.md) | Người triển khai: tạo app, quyền, nghiệm thu, bảng lỗi |
| [Mẫu trạm cấp token n8n](skill/lark-upload-video/references/mau-tram-n8n.md) | Không muốn để App Secret trên máy khách |

## 1. Cách hoạt động

```
Thư mục video trên máy
   │  lark_upload.py
   ├─ tenant_access_token (App ID + Secret, hoặc xin từ trạm n8n)
   ├─ drive/v1/medias/upload_all | upload_prepare/part/finish
   │     parent_type=bitable_file, parent_node=<base token>   -> file_token
   ├─ PUT bitable/v1/apps/<base>/tables/<table>/records/<id>   (file cũ + file mới)
   └─ đọc lại dòng -> OK -> chuyển file sang da-gui/
```

## 2. Chuẩn bị phía Lark (người triển khai làm, 10 phút)

1. **Tạo app**: [open.larksuite.com/app](https://open.larksuite.com/app) (Feishu: open.feishu.cn/app) → Create custom app. Nên **một khách một app**.
2. **Scope** (Permissions & Scopes, loại tenant): `bitable:app`. Nếu upload báo `99991672` đòi scope khác thì thêm đúng scope trong câu lỗi (thường là `drive:file:upload`). Dán link Wiki thay vì link Base thì cần thêm `wiki:wiki:readonly`.
3. **Bật Bot** (Features → Bot), rồi **Create version → Publish**. Mỗi lần thêm scope phải phát hành lại.
4. **Mời app vào Base**: Base → `…` → Thêm ứng dụng / Add app → chọn app → **Có thể chỉnh sửa**. Base bật quyền nâng cao: đưa app vào vai trò có quyền sửa bảng đích.
5. Base có một cột kiểu **Tệp đính kèm** (ví dụ `Video`). Kiểu "mỗi video một dòng": thêm cột văn bản `Tên file`. Kiểu "theo mã": cột mã phải không trùng.
6. Gửi khách **App ID** công khai, **App Secret** qua kênh riêng.

## 3. Cài trên máy khách

**Cách nhanh:** dán [PROMPT-MAY-KHACH.md](PROMPT-MAY-KHACH.md) cho AI agent trên máy khách.

**Cách tay:**
```powershell
New-Item -ItemType Directory -Force C:\LarkUpload | Out-Null
Invoke-WebRequest -UseBasicParsing -OutFile C:\LarkUpload\lark_upload.py https://raw.githubusercontent.com/huylamnguyen/lark-upload-video/main/skill/lark-upload-video/scripts/lark_upload.py
Invoke-WebRequest -UseBasicParsing -OutFile C:\LarkUpload\.env https://raw.githubusercontent.com/huylamnguyen/lark-upload-video/main/skill/lark-upload-video/templates/cau-hinh.mau.env
notepad C:\LarkUpload\.env      # điền App ID/Secret, link Base, tên cột, thư mục
cd C:\LarkUpload
python lark_upload.py --kiem-tra   # kiểm quyền + cột, không ghi
python lark_upload.py --dry        # liệt kê, không gửi
python lark_upload.py              # gửi
```

Gửi 1 file vào đúng dòng: `python lark_upload.py "D:\video\a.mp4" --record-id recXXXX`.

## 4. Cài làm Claude Code skill

```bash
git clone https://github.com/huylamnguyen/lark-upload-video
cp -r lark-upload-video/skill/lark-upload-video ~/.claude/skills/
```

## 5. Lưu ý

- Mỗi file tối đa 2 GB (giới hạn cột đính kèm Lark Base). Dung lượng lưu trữ tenant có hạn.
- Nên dùng MP4 H.264 để xem được ngay trong Lark; `.mov` HEVC từ iPhone có thể chỉ tải về được (chưa kiểm).
- Base bật quyền nâng cao mà upload báo lỗi quyền: thử `LARK_EXTRA={"bitablePerm":{"tableId":"tbl…","rev":1}}` (chưa kiểm).
- App Secret nằm trong `.env` trên máy khách; app chỉ vào được các Base đã mời nó. Không muốn để secret trên máy: xem [mẫu trạm n8n](skill/lark-upload-video/references/mau-tram-n8n.md).
