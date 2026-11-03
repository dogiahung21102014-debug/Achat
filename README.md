# Achat V2.2 — Meta OAuth + Quản trị viên (BETA)

Đây là bản phát triển tiếp từ V2.1, **KHÔNG PHẢI sản phẩm sẵn sàng thương mại**.

## Có gì mới
- Super Admin chính tạo và khóa Super Admin phụ, nhật ký thao tác.
- Facebook Login OAuth (server-side authorization code, state), lưu Page token bằng Fernet.
- Liệt kê Page và giới hạn số lượng theo shop, không chiếm Page đã kết nối với shop khác.
- Webhook GET verify và POST kiểm tra chữ ký SHA-256, chống trùng message id, lưu tin nhắn theo shop.
- Gửi tin nhắn Messenger qua Graph API với quyền của Page khi hội thoại có Page-scoped sender ID.
- Giữ giao diện ba cột, quản lý shop, nhân viên, sản phẩm và đơn nháp của V2.1.

## Triển khai
1. Sao lưu cơ sở dữ liệu V2.1 trước khi nâng cấp. Trên Render Free không có ổ đĩa bền vững mặc định; SQLite có nguy cơ mất dữ liệu khi triển khai lại. Chưa nên nhập dữ liệu thật.
2. Đưa **nội dung bên trong** thư mục `achat_v2_2` lên thư mục gốc repository GitHub, giữ nguyên `templates/`, `static/`, `Dockerfile`.
3. Render chọn Web Service, Docker, branch main, Root Directory để trống.
4. Thiết lập SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, APP_ENV=production. Với SQLite chỉ để thử nghiệm: không đặt DATABASE_PATH=/data/... trừ khi đã gắn persistent disk. Nếu nâng cấp từ bản demo, giữ DB hiện có nếu cần dữ liệu cũ.
5. Tạo TOKEN_ENCRYPTION_KEY bằng `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Giữ bí mật khóa; mất khóa sẽ không giải mã được token.
6. Điền META_APP_ID, META_APP_SECRET, META_VERIFY_TOKEN, TOKEN_ENCRYPTION_KEY trong Render > Environment. Không đăng lên GitHub.
7. Meta > Facebook Login > Valid OAuth Redirect URIs: `https://achat-rsya.onrender.com/facebook/callback` (thay bằng tên miền của bạn nếu khác).
8. Meta > Webhooks > Page: Callback URL `https://achat-rsya.onrender.com/facebook/webhook`, Verify Token phải trùng META_VERIFY_TOKEN. Bật messages và messaging_postbacks khi được Meta cấp quyền.
9. Đăng nhập chủ shop > Fanpage > Kết nối Facebook, rồi nhấn Đăng ký nhận tin trên từng page.

## Giới hạn quan trọng
- Phải được Meta cấp các quyền phù hợp (pages_show_list, pages_messaging, pages_manage_metadata); ứng dụng chưa được phê duyệt có thể chỉ hoạt động với tài khoản vai trò ứng dụng.
- Chưa có hàng đợi webhook, retry, đồng bộ lịch sử, token lifecycle, Facebook comment, phân quyền chi tiết theo hội thoại, AI Agent thật, vận chuyển thật, in vận đơn, PostgreSQL, billing, 2FA và kiểm thử tải.
- Webhook hiện xử lý đồng bộ, phù hợp thử nghiệm nhỏ, không đủ bền vững cho tải thương mại.
- SQLite không phù hợp triển khai nhiều instance hoặc lưu dữ liệu production trên filesystem tạm.
- Chỉ dùng để thử nghiệm nội bộ, không kết nối Page bán hàng thật cho đến khi bảo mật, sao lưu và chính sách dữ liệu được kiểm tra.
