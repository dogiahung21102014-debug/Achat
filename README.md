# Achat — Bản demo web (chưa dùng kinh doanh thật)

## Cài trên iMac
Mở Terminal, di chuyển đến thư mục giải nén, ví dụ:
```bash
cd ~/Downloads/achat_demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python3 app.py
```
Mở `http://127.0.0.1:5000` trên trình duyệt.

## Tài khoản demo
- `admin` / `Achat@123`: chủ hệ thống
- `dan` / `Achat@123`: chủ shop Đan Đan
- `nhanvien` / `Achat@123`: nhân viên
- `thoitrang` / `Achat@123`: chủ shop thứ hai

## Đưa mã nguồn lên GitHub
1. Tạo repository **riêng tư** tên `achat`.
2. Trong Terminal tại thư mục ứng dụng:
```bash
git init
git add .
git commit -m "Achat demo"
git branch -M main
git remote add origin https://github.com/TEN_TAI_KHOAN/achat.git
git push -u origin main
```
Thay TEN_TAI_KHOAN bằng tài khoản GitHub. GitHub lưu mã nguồn chứ không tự chạy ứng dụng Flask.

## Triển khai demo lên hosting Docker (ví dụ Render)
1. Kết nối GitHub repository với dịch vụ hosting có hỗ trợ Docker.
2. Chọn Dockerfile của dự án và tạo dịch vụ web.
3. Đặt biến môi trường `SECRET_KEY` là chuỗi bí mật dài, ngẫu nhiên.
4. Chạy container cổng 8080, mở URL hosting cung cấp; `/health` dùng kiểm tra tình trạng.

**Cảnh báo quan trọng:** Không dùng bản demo này để xử lý khách hàng thật trên Internet. Mật khẩu mẫu công khai, chưa có CSRF, rate limiting, quản lý phiên nâng cao, cơ sở dữ liệu PostgreSQL và bảo mật production. SQLite trên hosting container có thể mất dữ liệu khi triển khai lại. Chỉ nên chạy localhost hoặc môi trường thử nghiệm riêng tư.

## Những gì đã có
Giao diện tiếng Việt, 3 cột hội thoại, phân quyền cơ bản theo shop, hashtag màu, sản phẩm SKU, chốt và lưu đơn, lọc đơn, đẩy đơn giả lập, AI Check quy tắc đơn giản.

## Những gì chưa có
Kết nối Facebook OAuth/Messenger thật, FB Agent, AI thật, vận chuyển BEST/GHN/GHTK, in vận đơn PDF, Excel, phân công hội thoại cho nhân viên, lọc nâng cao, báo cáo tài chính và hạ tầng production.

**AI Check** chỉ nhận diện SKU, số lượng, số điện thoại và địa chỉ bằng biểu thức mẫu. Nó không hiểu ngữ cảnh tự nhiên như mô hình AI, có thể sai hoặc tạo trùng đơn; không được sử dụng tự động với khách thật.
