# Hướng Dẫn Deploy lên Render

## Tổng Quan
- **Frontend** (web folder) → Cloudflare Pages ✅ (đã deploy)
- **Backend** (api_server.py) → Render Web Service (đang deploy)

---

## BƯỚC 1: Chuẩn Bị Environment Variable cho Render

### 1.1 Encode Service Account JSON

Chạy lệnh này trên máy của bạn:
```bash
python encode_service_account.py
```

Kết quả sẽ in ra base64 string, **copy toàn bộ string này**.

---

## BƯỚC 2: Deploy lên Render

### 2.1 Truy cập Render Dashboard
- Vào https://dashboard.render.com
- Click **"New +"** → **"Web Service"**

### 2.2 Kết nối GitHub
- Click **"Connect Repository"**
- Chọn `quoctichle/tinnhantudong`
- Click **"Connect"**

### 2.3 Cấu hình Service

Điền các trường sau:

| Field | Value |
|-------|-------|
| **Service Name** | `tinnhan-api` |
| **Region** | `Singapore` |
| **Branch** | `main` |
| **Root Directory** | (trống) |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn api_server:app --host 0.0.0.0 --port 8000` |

### 2.4 Thêm Environment Variables

Scroll xuống, click **"Add Environment Variable"**:

| Key | Value |
|-----|-------|
| `FB_EMAIL` | `0886544032` |
| `FB_PASSWORD` | `linhlinh22` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_B64` | **[PASTE base64 string từ bước 1.1]** |
| `CHROME_USER_DATA_DIR` | `/tmp/chrome-profile` |
| `CHROME_PROFILE` | `Default` |

### 2.5 Deploy
- Click **"Create Web Service"**
- Render sẽ tự động build và deploy
- Chờ status thành "Live" (2-3 phút)

---

## BƯỚC 3: Lấy URL Backend

Khi deploy thành công:
- URL backend sẽ có dạng: `https://tinnhan-api.onrender.com`
- Copy URL này

---

## BƯỚC 4: Cập nhật Frontend

### 4.1 Mở web UI (Cloudflare Pages)
- Vào trang web của bạn
- Click biểu tượng **⚙️ Settings**

### 4.2 Thiết lập API URL
- Dán URL backend vào trường **"API Base URL"**
- Ví dụ: `https://tinnhan-api.onrender.com`
- Click **"Save"**

---

## BƯỚC 5: Test

Quay lại web UI:
1. Kiểm tra **Status**: phải có dòng "API Status: ✓ Connected"
2. Click nút "Send Exchange Notification" để test
3. Nếu thành công → mọi người có thể dùng!

---

## Troubleshooting

### "Failed to fetch" error
- Check: API URL có đúng không?
- Check: Render service status = "Live"?
- Check: Environment variables nhập đúng không?

### "Chrome not found"
- Render free tier không có Chrome pre-installed
- **Fix**: Cần nâng lên paid tier hoặc dùng Browserless.io

### "Service account not found"
- Check: GOOGLE_SERVICE_ACCOUNT_JSON_B64 nhập đúng không?
- Thử: Chạy lại `python encode_service_account.py`

---

## Notes

- Render free tier có giới hạn (15 min idle → sleep)
- Nếu cần 24/7, upgrade lên Render Starter ($7/tháng)
- Chrome profile sẽ reset mỗi khi deploy (tùy thiết lập persistent volume)
