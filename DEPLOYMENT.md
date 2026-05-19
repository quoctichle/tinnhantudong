# SunShine Message Control Deployment

## 1. Kiến trúc đúng cho bài toán này

Cloudflare Pages chỉ phù hợp để host frontend tĩnh.

Ba file sau đang dùng Selenium + Chrome profile:
- send_messages_bot.py
- send_messages_cuoc.py
- send_messages_refund.py

Các file này khong the chay truc tiep tren Cloudflare Workers hoac Cloudflare Pages.

Kien truc nen dung:
- Frontend: folder web/ deploy len Cloudflare Pages
- Backend: chay api_server.py tren may Windows/VPS/Render/Railway co Python va Chrome
- Frontend bam nut -> goi API backend -> backend chay script tuong ung

## 2. Chay backend local

Tao va kich hoat virtualenv nhu ban dang dung, sau do cai them goi:

```powershell
pip install -r requirements-webapi.txt
```

Chay API:

```powershell
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Neu muon gioi han origin frontend:

```powershell
$env:ALLOWED_ORIGINS="https://your-project.pages.dev"
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

## 3. Deploy frontend len Cloudflare Pages

Folder deploy la:
- web/

Cach nhanh nhat:
1. Tao Git repo va push len GitHub
2. Vao Cloudflare Pages
3. Chon Create project
4. Connect repo
5. Chon thu muc web/
6. Build command: de trong
7. Build output directory: web

Vi day la static site, ban cung co the upload truc tiep noi dung folder web/ len Pages.

## 4. Cau hinh frontend

Sau khi mo web, nhap API base URL vao o cau hinh:
- local: http://127.0.0.1:8000
- server that: https://api-your-domain.com

Nhan Luu, sau do nhan Kiem tra.

## 5. API co san

- GET /api/health
- GET /api/jobs
- POST /api/jobs/exchange/run
- POST /api/jobs/billing/run
- POST /api/jobs/refund/run

## 6. Luu y van hanh

- API da khoa 1 job tai 1 thoi diem vi 3 script dang dung chung Chrome profile
- Neu muon chay dong thoi nhieu job, can tach chrome-profile rieng cho tung script
- Service account JSON va chrome-profile khong nen dua len Cloudflare hoac frontend
