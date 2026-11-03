# Achat V2 — Bản nền tảng quản lý đa shop (MVP demo)

## Đã có
- Giao diện tiếng Việt theo bố cục Sapo Social tham khảo, thiết kế riêng cho Achat.
- **Superadmin riêng** `/admin`: tạo shop, cấp thời hạn dùng thử mặc định 7 ngày, giới hạn page/nhân viên, gia hạn và khóa/mở shop, nhật ký thao tác.
- **Shop riêng**: inbox 3 cột, hội thoại và nhãn, sản phẩm, đơn nháp, nhân viên với vai trò owner/manager/staff, danh sách page demo.
- **Tách dữ liệu theo shop** bằng `shop_id` và lọc trong các truy vấn; mật khẩu hash; xác thực session.
- **AI Check demo**: tìm SKU, số lượng, số điện thoại trong tin nhắn, tạo đơn nháp (không phải AI thực).

## Chưa có / KHÔNG dùng kinh doanh thật
- Chưa có Facebook OAuth, webhook, Messenger thật, FB Agent, AI LLM thật, đơn vị vận chuyển thật, thanh toán, đa kho, báo cáo thực, reset mật khẩu, CSRF, rate limiting, MFA, hàng đợi background, PostgreSQL, migrations và kiểm thử bảo mật độc lập.
- SQLite cục bộ **không bền vững trên Render filesystem mặc định**: dữ liệu có thể mất sau restart/deploy. Để dùng thật cần PostgreSQL + backup.
- Tài khoản demo có mật khẩu mặc định; bắt buộc đổi trước khi công khai.
- Hệ thống có nền tảng phân quyền, nhưng **chưa đủ chuẩn bảo mật sản phẩm SaaS**.

## Chạy trên iMac
```bash
cd achat_v2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python3 app.py
```
Mở `http://127.0.0.1:8080`

## Đăng nhập thử
- Superadmin: `admin@achat.local` / `ChangeMe123!`
- Chủ shop: `owner@achat.local` / `ChangeMe123!`

Có thể đặt mật khẩu khởi tạo bằng biến `ADMIN_PASSWORD` và `DEMO_OWNER_PASSWORD` **trước lần khởi tạo database đầu tiên**. Nếu database đã có, các biến này không đổi mật khẩu.

## Triển khai Render
1. Upload **toàn bộ file và thư mục** của dự án lên GitHub, thay thế bộ demo cũ.
2. Render → Web Service → chọn repo → Language: Docker → Branch: main → Root Directory: trống.
3. Environment: đặt `SECRET_KEY`, `ADMIN_PASSWORD`, `DEMO_OWNER_PASSWORD`, `DATABASE_PATH` (nếu có persistent disk).
4. Deploy. Truy cập đường dẫn Render cung cấp.
5. Chỉ sử dụng để **trình diễn**, không lưu thông tin khách thật.

## Lộ trình bản thương mại
1. PostgreSQL, Alembic migrations, CSRF, auth nâng cao, API đa tenant và audit đầy đủ.
2. Meta OAuth, page permissions, webhook, Messenger sync và outbound messages.
3. Catalog biến thể, kho, checkout và đối soát đơn.
4. AI agent có xác nhận của khách và cơ chế tránh đơn trùng, chuyển giao nhân viên.
5. API GHN/GHTK/BEST/Viettel Post..., batch push và in nhãn.
6. Subscription, quota, hóa đơn, bảo mật, monitoring và triển khai đa khách hàng.
