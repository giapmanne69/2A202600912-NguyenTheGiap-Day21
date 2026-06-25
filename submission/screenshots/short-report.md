# BÁO CÁO TỔNG KẾT LAB MLOps

## 1. Bộ siêu tham số đã chọn và lý do (Kết quả Bước 1)
Sau khi thực hiện chạy các thí nghiệm huấn luyện mô hình Random Forest trên tập dữ liệu ban đầu (Phase 1) và so sánh thông qua giao diện MLflow UI, bộ siêu tham số được chọn tối ưu nhất là:
* **`n_estimators` (Số lượng cây)**: `200`
* **`max_depth` (Độ sâu tối đa)**: `20`
* **`min_samples_split` (Mẫu tối thiểu phân chia)**: `2`

### Lý do lựa chọn:
* **Tính tối ưu**: Đạt độ chính xác cao nhất trên tập đánh giá (Accuracy = **`0.6840`**, F1-Score = **`0.6830`**).
* **Tránh Overfitting/Underfitting**: Với độ sâu `max_depth = 5`, mô hình bị underfitting (chỉ đạt ~`0.562`). Tăng lên `20` cải thiện hiệu năng vượt bậc.
* **Hiệu năng thực tế**: Khi bổ sung dữ liệu Phase 2 ở Bước 3, mô hình sử dụng bộ siêu tham số tối ưu này đã tăng vọt độ chính xác lên **`0.7540`** (F1-Score = **`0.7534`**), chứng minh tính tổng quát hóa tốt.

---

## 2. Khó khăn gặp phải và phương án giải quyết

Trong quá trình thiết lập pipeline CI/CD và triển khai lên AWS EC2 VM, nhóm đã gặp một số khó khăn kỹ thuật và giải quyết như sau:

| STT | Khó khăn gặp phải | Nguyên nhân | Cách giải quyết |
| :---: | :--- | :--- | :--- |
| **1** | Lỗi tạo S3 Bucket (`AccessDenied`) và EC2 Security Group | Quyền hạn tài khoản IAM mặc định bị giới hạn chặt chẽ (không có quyền `s3:CreateBucket` và `ec2:CreateSecurityGroup`). | Sử dụng S3 Bucket được cấp sẵn (`depvinai`) để lưu trữ DVC và yêu cầu Admin cấu hình/cấp quyền bổ sung hoặc dùng VM có sẵn. |
| **2** | Lỗi `MissingConfigException` khi chạy MLflow trên GitHub Actions runner | File cấu hình môi trường `.env` bị bỏ qua bởi Git, khiến runner mặc định ghi dữ liệu vào `./mlruns` bị thiếu cấu hình mặc định (`meta.yaml`). | Cấu hình mặc định trong [`src/train.py`](file:///e:/VinAI/D21-25.6.2026/2A202600912-NguyenTheGiap-Day21/src/train.py) để tự động khởi tạo và ghi log vào SQLite (`sqlite:///mlflow.db`) nếu không tìm thấy biến môi trường. |
| **3** | Lỗi `dvc-s3` (No module named `dvc_s3`) trên GitHub runner | File `requirements.txt` ban đầu cấu hình gói hỗ trợ GCS (`dvc[gs]`) chứ không phải AWS S3. | Cập nhật file [`requirements.txt`](file:///e:/VinAI/D21-25.6.2026/2A202600912-NguyenTheGiap-Day21/requirements.txt) chuyển sang gói **`dvc[s3]`** và bổ sung **`boto3`** cho AWS. |
| **4** | Lỗi `oauth-app-workflow-scope` khi `git push` | Token hoặc phương thức đăng nhập Git trên máy tính cá nhân thiếu quyền sửa đổi tệp workflow của GitHub Actions. | Tạo lại một **Personal Access Token (classic)** trên GitHub và tích chọn phạm vi quyền **`workflow`**, sau đó cập nhật lại Git URL. |
| **5** | Dịch vụ `mlops-serve.service` trên VM bị lỗi `status=203/EXEC` | File cấu hình systemd service trỏ vào trình dịch Python của Virtual Environment (`/home/ubuntu/venv/bin/python`) vốn không tồn tại trên VM. | Sửa file cấu hình dịch vụ trên máy ảo trỏ về trình dịch Python hệ thống (`/usr/bin/python3`) và reload lại dịch vụ. |
| **6** | Lỗi gọi API POST `/predict` bằng `curl` trên Windows PowerShell | Lệnh `curl` trên Windows mặc định bị alias thành `Invoke-WebRequest` dẫn đến sai cú pháp Header `-H`. | Thay đổi lệnh gọi kiểm thử bằng cách sử dụng công cụ nguyên bản **`curl.exe`** hoặc cmdlet **`Invoke-RestMethod`** của PowerShell. |
