# Hai mẫu dùng n8n làm trạm

## Mẫu 1 — Trạm CẤP TOKEN (dùng cho video)

Máy khách không giữ App Secret. n8n giữ secret và chỉ trả `tenant_access_token` (sống ≤ 2 giờ). Video đi **thẳng** từ máy lên Lark, không qua n8n.

Workflow 4 node, **không dùng Code node** (task runner n8n dễ quá tải, trả 500 "Task request timed out after 60 seconds"):

1. **Webhook** — POST `/<khach>-cap-token-upload`, Respond: *Using 'Respond to Webhook' node*.
2. **Crypto** — Hash SHA256, encoding hex, value `{{ $json.headers['x-upload-key'] || '' }}`, lưu vào `vanTay`.
3. **IF** — `{{ ["<sha256 khoá máy 1>","<sha256 khoá máy 2>"].includes($json.vanTay) }}` là true. Nhánh false → **Respond to Webhook** mã 401 `{"loi":"KHOA_KHONG_HOP_LE"}`.
4. **HTTP Request** — POST `https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal`, body `{"app_id": "...", "app_secret": "..."}` (để trong credential, không viết thẳng vào node) → **Respond to Webhook** trả `{{ JSON.stringify({ tenant_access_token: $json.tenant_access_token, expire: $json.expire }) }}`.

n8n chỉ lưu **mã băm** của khoá. Tạo khoá: `python -c "import secrets;print(secrets.token_urlsafe(32))"`, băm: `python -c "import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" <khoá>`.

`.env` trên máy khách: bỏ `LARK_APP_ID/SECRET`, thêm
```
TOKEN_URL=https://<n8n>/webhook/<khach>-cap-token-upload
TOKEN_KEY=<khoá gốc của máy này>
```
Thu hồi một máy = xoá mã băm của nó khỏi node IF.

## Mẫu 2 — Trạm NHẬN FILE (chỉ file nhỏ ≤ 10 MB: ảnh, PDF scan)

Máy khách không có token nào. Máy POST JSON `{maDon, tenFile, soByte, noiDungB64}` + header khoá riêng; n8n kiểm khoá → tìm dòng theo mã → *Convert to File* (base64 → binary) → HTTP multipart `upload_all` (`parent_type=bitable_file`, `parent_node=<base token>`) → đọc ô cũ → PUT cũ + mới → đọc lại → trả JSON.

**Không dùng cho video:** qua URL công khai của n8n, gói ~12 MB đi được, ~16 MB bị gãy; base64 làm file phình thêm 33%; n8n giữ nguyên gói trong RAM nên dễ kéo sập instance dùng chung. Chặn trần 10 MB ở cả máy khách lẫn n8n.

Kinh nghiệm khi làm mẫu 2:
- Chặn gửi trùng theo **tên + dung lượng** trên chính dòng đích, trả 409 để máy khách coi như xong — máy khách sẽ gửi lại khi gặp 5xx.
- Máy khách tự gửi lại khi 5xx (chờ 10 s, rồi 30 s); **không** gửi lại khi 4xx.
- Không lưu execution lỗi nếu gói chứa giấy tờ nhạy cảm → phải có cách khác để biết lỗi (errorWorkflow, đếm lượt gọi).
