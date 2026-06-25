# Bước 2 - Pipeline CI/CD Tự Động

Mục tiêu: Mỗi khi bạn push code hoặc thay đổi dữ liệu, GitHub Actions tự động huấn luyện mô hình, kiểm tra accuracy có đạt ngưỡng >= 0.65 không, và triển khai lên VM nếu đạt yêu cầu.

Thời gian ước tính: 4-5 giờ

---

## Lựa Chọn Cloud Provider

Bạn sẽ sử dụng **AWS (Amazon Web Services)** cho phần này. Ánh xạ các khái niệm như sau:

| Khái niệm | AWS |
|---|---|
| Object Storage | Amazon S3 |
| VM | EC2 |
| CLI | `aws` CLI |
| DVC storage extra | `dvc[s3]` |
| Cloud SDK Python | `boto3` |
| Credentials | AWS Access Key ID / Secret Access Key |

---

## 2.1 Tạo Cloud Storage Bucket (Amazon S3)

Tên bucket phải là duy nhất trên toàn cầu. Thay thế `<BUCKET_NAME>` và `<AWS_REGION>` bằng giá trị của bạn.

**Windows (PowerShell):**
```powershell
$env:BUCKET="<BUCKET_NAME>"
$env:AWS_DEFAULT_REGION="us-east-1"

# Tạo S3 bucket
aws s3 mb s3://$env:BUCKET --region $env:AWS_DEFAULT_REGION
```

**Linux / macOS:**
```bash
export BUCKET=<BUCKET_NAME>
export AWS_DEFAULT_REGION=us-east-1

# Tạo S3 bucket
aws s3 mb s3://$BUCKET --region $AWS_DEFAULT_REGION
```

---

## 2.2 Tạo Cloud Credentials (IAM User)

Tạo IAM User với quyền tối thiểu để truy cập bucket S3 của bạn.

1. Tạo một IAM User:
```bash
aws iam create-user --user-name mlops-lab-user
```

2. Tạo chính sách (policy) truy cập S3 chỉ cho bucket cụ thể của bạn:
```bash
# Tạo file s3-policy.json
cat <<EOF > s3-policy.json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::$BUCKET",
                "arn:aws:s3:::$BUCKET/*"
            ]
        }
    ]
}
EOF

# Đăng ký policy này lên AWS
aws iam create-policy --policy-name mlops-s3-policy --policy-document file://s3-policy.json
```

3. Gắn policy vào IAM User (thay thế `<ACCOUNT_ID>` bằng AWS Account ID của bạn):
```bash
aws iam attach-user-policy \
  --user-name mlops-lab-user \
  --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/mlops-s3-policy
```

4. Tạo Access Key ID và Secret Access Key cho user này:
```bash
aws iam create-access-key --user-name mlops-lab-user
```
Lưu lại `AccessKeyId` và `SecretAccessKey` thu được. Không lưu chúng trong git.

---

## 2.3 Cài Đặt DVC Với Cloud Storage Remote

```bash
dvc init

# Trỏ DVC đến AWS S3 bucket:
dvc remote add -d myremote s3://$BUCKET/dvc

# Cấu hình credentials (sử dụng Access Key vừa tạo):
# AWS tự động đọc từ ~/.aws/credentials hoặc từ biến môi trường AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

# Theo dõi các file dữ liệu bằng DVC
dvc add data/train_phase1.csv
dvc add data/eval.csv
dvc add data/train_phase2.csv

# Commit các file con trỏ DVC vào git (KHÔNG phải file CSV)
git add data/train_phase1.csv.dvc data/eval.csv.dvc data/train_phase2.csv.dvc \
        .gitignore .dvc/config
git commit -m "feat: track datasets with DVC"

# Thiết lập biến môi trường AWS để DVC push
# Windows (PowerShell):
$env:AWS_ACCESS_KEY_ID="<AccessKeyId>"
$env:AWS_SECRET_ACCESS_KEY="<SecretAccessKey>"
# Linux/macOS:
export AWS_ACCESS_KEY_ID="<AccessKeyId>"
export AWS_SECRET_ACCESS_KEY="<SecretAccessKey>"

# Đẩy các file CSV lên S3
dvc push
```

Xác nhận trên AWS S3 Console rằng các file dữ liệu đã xuất hiện dưới prefix `dvc/` trong bucket.

---

## 2.4 Tạo VM Trên Cloud (AWS EC2)

1. Tạo Security Group cho VM:
```bash
aws ec2 create-security-group \
  --group-name mlops-sg \
  --description "Security group for MLOps server"
```

2. Mở cổng 22 (SSH) và cổng 8000 (API) cho Security Group:
```bash
aws ec2 authorize-security-group-ingress --group-name mlops-sg --protocol tcp --port 22 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-name mlops-sg --protocol tcp --port 8000 --cidr 0.0.0.0/0
```

3. Khởi chạy một instance EC2 Ubuntu 22.04 LTS (thay đổi `--key-name` bằng key pair của bạn):
```bash
aws ec2 run-instances \
  --image-id ami-053b0d53c279acc90 \
  --count 1 \
  --instance-type t2.micro \
  --key-name <YOUR_KEY_PAIR_NAME> \
  --security-groups mlops-sg
```

4. Lấy IP công khai (Public IP) của VM:
```bash
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" "Name=group-name,Values=mlops-sg" \
  --query "Reservations[*].Instances[*].PublicIpAddress" \
  --output text
```

---

## 2.5 Cấu Hình VM (Thực Hiện Một Lần, Thủ Công)

SSH vào VM bằng private key của key pair:

```bash
ssh -i <YOUR_KEY>.pem ubuntu@<VM_IP>
```

Bên trong VM, cài đặt các thư viện cần thiết:

```bash
sudo apt update && sudo apt install -y python3-pip
pip3 install fastapi uvicorn scikit-learn joblib boto3

mkdir -p ~/models ~/src ~/.aws
```

Tạo file `~/.aws/credentials` trên VM chứa AWS credentials vừa tạo của `mlops-lab-user` để Python SDK (`boto3`) có thể đọc được:

```bash
cat <<EOF > ~/.aws/credentials
[default]
aws_access_key_id = <AccessKeyId>
aws_secret_access_key = <SecretAccessKey>
EOF
```

Thoát khỏi VM.

---

## 2.6 Viết `src/serve.py`

Tạo file `src/serve.py` theo khung dưới đây. File này chạy trên VM và cung cấp REST API để nhận yêu cầu suy luận.

Nhiệm vụ:
1. Khi khởi động, tải file `model.pkl` từ S3 về máy.
2. Cung cấp endpoint `GET /health` trả về trạng thái server.
3. Cung cấp endpoint `POST /predict` nhận 12 đặc trưng và trả về nhãn dự đoán.

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import boto3
import joblib
import os

app = FastAPI()

# Đọc cấu hình từ biến môi trường
AWS_BUCKET = os.environ["AWS_BUCKET"]
AWS_MODEL_KEY = "models/latest/model.pkl"
MODEL_PATH = os.path.expanduser("~/models/model.pkl")


def download_model():
    """Tải file model.pkl từ S3 về máy khi server khởi động."""
    # TODO 2.6.1: Tạo boto3 s3 client
    # TODO 2.6.2: Gọi s3.download_file(AWS_BUCKET, AWS_MODEL_KEY, MODEL_PATH)
    # TODO 2.6.3: In thông báo thành công
    pass  # xóa dòng này khi đã viết xong


# Gọi hàm này khi module được import (chạy khi server khởi động)
download_model()
model = joblib.load(MODEL_PATH)


class PredictRequest(BaseModel):
    features: list[float]


@app.get("/health")
def health():
    """Endpoint kiểm tra sức khỏe server. GitHub Actions dùng endpoint này để xác nhận deploy thành công."""
    # TODO 2.6.4: Trả về dict {"status": "ok"}
    pass  # xóa dòng này khi đã viết xong


@app.post("/predict")
def predict(req: PredictRequest):
    """
    Endpoint suy luận.

    Đầu vào: JSON {"features": [f1, f2, ..., f12]}
    Đầu ra:  JSON {"prediction": <0|1|2>, "label": <"thấp"|"trung_bình"|"cao">}
    """
    # TODO 2.6.5: Kiểm tra len(req.features) == 12.
    #   Nếu không, raise HTTPException(status_code=400, detail="Expected 12 features (wine quality)")

    # TODO 2.6.6: Gọi model.predict([req.features]) để lấy kết quả dự đoán.

    # TODO 2.6.7: Trả về dict chứa "prediction" (int) và "label" (string).
    #   Nhãn: 0 -> "thấp", 1 -> "trung_bình", 2 -> "cao"
    pass  # xóa dòng này khi đã viết xong


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Upload file `serve.py` lên VM:

```bash
scp -i <YOUR_KEY>.pem src/serve.py ubuntu@<VM_IP>:~/src/serve.py
```

---

## 2.7 Cấu Hình Systemd Service Trên VM

SSH trở lại vào VM:

```bash
ssh -i <YOUR_KEY>.pem ubuntu@<VM_IP>
```

Tạo file service để server tự động khởi động lại khi VM reboot:

```bash
sudo tee /etc/systemd/system/mlops-serve.service > /dev/null <<EOF
[Unit]
Description=MLOps Model Inference Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
Environment="AWS_BUCKET=<YOUR_BUCKET_NAME>"
Environment="AWS_DEFAULT_REGION=<AWS_REGION>"
ExecStart=/usr/bin/python3 /home/ubuntu/src/serve.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mlops-serve
```

Thay `<YOUR_BUCKET_NAME>` và `<AWS_REGION>` bằng tên thực tế của bạn trước khi chạy.

Chưa cần khởi động service lúc này. Model chưa có trên S3 cho đến khi pipeline CI/CD chạy lần đầu tiên.

---

## 2.8 Tạo SSH Key Để GitHub Actions Deploy

Chạy trên máy tính cá nhân (không phải VM):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/mlops_deploy -N "" -C "github-actions-deploy"
```

Thêm public key vào VM:

```bash
ssh -i <YOUR_KEY>.pem ubuntu@<VM_IP> "echo '$(cat ~/.ssh/mlops_deploy.pub)' >> ~/.ssh/authorized_keys"
```

---

## 2.9 Thêm GitHub Secrets

Vào repo GitHub: Settings > Secrets and variables > Actions > New repository secret.

Thêm chính xác các secrets sau:

| Tên secret | Cách lấy giá trị |
|---|---|
| AWS_ACCESS_KEY_ID | Access Key ID của IAM User `mlops-lab-user` |
| AWS_SECRET_ACCESS_KEY | Secret Access Key của IAM User `mlops-lab-user` |
| AWS_DEFAULT_REGION | Region ví dụ `us-east-1` |
| CLOUD_BUCKET | Tên S3 bucket (ví dụ: `my-mlops-bucket`) |
| VM_HOST | IP công khai của EC2 VM (từ bước 2.4) |
| VM_USER | `ubuntu` |
| VM_SSH_KEY | Dán toàn bộ nội dung file `~/.ssh/mlops_deploy` (private key) |

---

## 2.10 Viết `tests/test_train.py`

*(Nội dung này giữ nguyên, do unit test sử dụng dữ liệu giả lập trong bộ nhớ và chạy cục bộ không cần kết nối cloud)*

---

## 2.11 Viết `.github/workflows/mlops.yml`

Tạo file `.github/workflows/mlops.yml` theo cấu trúc dưới đây, đã chuyển sang dùng AWS S3:

```yaml
name: MLOps Pipeline

on:
  push:
    branches: [main]
    paths:
      - 'data/**.dvc'
      - 'src/**.py'
      - 'params.yaml'
  workflow_dispatch:

jobs:

  # JOB 1: Chạy unit tests trên dữ liệu giả (không cần S3)
  test:
    name: Test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest tests/ -v

  # JOB 2: Huấn luyện mô hình, upload model lên S3
  train:
    name: Train
    needs: test
    runs-on: ubuntu-latest
    outputs:
      accuracy: ${{ steps.read_metrics.outputs.accuracy }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_DEFAULT_REGION }}

      - name: Pull data with DVC
        run: dvc pull

      - name: Train model
        run: python src/train.py

      - name: Read metrics
        id: read_metrics
        run: |
          python -c "
          import json
          with open('outputs/metrics.json') as f:
              m = json.load(f)
              print(f'accuracy={m[\"accuracy\"]}')
          " >> $GITHUB_OUTPUT

      - name: Upload model to S3
        run: |
          python -c "
          import boto3, os
          s3 = boto3.client('s3')
          s3.upload_file('models/model.pkl', '${{ secrets.CLOUD_BUCKET }}', 'models/latest/model.pkl')
          "

      - name: Save metrics as artifact
        uses: actions/upload-artifact@v4
        with:
          name: metrics
          path: outputs/metrics.json

  # JOB 3: Kiểm tra chất lượng - chỉ cho phép deploy khi accuracy >= 0.70
  eval:
    name: Eval
    needs: train
    runs-on: ubuntu-latest
    steps:
      - name: Check eval gate
        run: |
          python -c "
          acc = float('${{ needs.train.outputs.accuracy }}')
          if acc < 0.70:
              print(f'Accuracy {acc:.4f} < 0.70. Deployment rejected.')
              import sys; sys.exit(1)
          else:
              print(f'Accuracy {acc:.4f} >= 0.70. Deployment approved.')
          "

  # JOB 4: Triển khai sau khi eval gate qua
  deploy:
    name: Deploy
    needs: eval
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to EC2
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.VM_HOST }}
          username: ${{ secrets.VM_USER }}
          key: ${{ secrets.VM_SSH_KEY }}
          script: |
            sudo systemctl restart mlops-serve
            sleep 5
            curl -f http://localhost:8000/health || exit 1
```

---

## 2.12 Lần Chạy Pipeline Đầu Tiên

Tạo hai file con trong `src/` và `tests/` để Python có thể import module:

```bash
touch src/__init__.py tests/__init__.py
```

Push tất cả lên GitHub:

```bash
git add .
git commit -m "feat: add AWS CI/CD pipeline, tests, and serving API"
git push origin main
```

Theo dõi pipeline trong tab **Actions** trên repo GitHub.

Sau khi pipeline chạy thành công và model đã được upload lên S3, khởi động service trên VM:

```bash
ssh -i <YOUR_KEY>.pem ubuntu@<VM_IP> "sudo systemctl start mlops-serve"
```

Thử nghiệm endpoint:

```bash
VM_IP=<YOUR_VM_IP>

# Kiểm tra sức khỏe
curl http://$VM_IP:8000/health

# Dự đoán (12 đặc trưng theo thứ tự trong FEATURE_NAMES)
curl -X POST http://$VM_IP:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"features": [7.4, 0.70, 0.00, 1.9, 0.076, 11.0, 34.0, 0.9978, 3.51, 0.56, 9.4, 0]}'
```

Kết quả mong đợi:

```json
{"prediction": 0, "label": "thấp"}
```

---

## Xử Lý Sự Cố

**`dvc push` thất bại với lỗi xác thực**

Xác nhận biến môi trường `AWS_ACCESS_KEY_ID` và `AWS_SECRET_ACCESS_KEY` đã được thiết lập đúng trong phiên làm việc hiện tại của terminal.

**Service trên VM không khởi động được**

Xem log của service:

```bash
sudo journalctl -u mlops-serve -n 50
```

Nguyên nhân phổ biến:
- Biến môi trường `AWS_BUCKET` sai trong file service.
- AWS Credentials của VM chưa được cấu hình đúng trong `~/.aws/credentials`.
- File model chưa tồn tại trên S3.

---

## Kết Quả Cần Đạt - Bước 2

- Cả bốn GitHub Actions jobs (Unit Test, Train, Eval, Deploy) đều hoàn thành thành công (màu xanh).
- `curl http://VM_IP:8000/health` trả về `{"status": "ok"}`.
- S3 Console hiển thị file dữ liệu dưới `dvc/` và file model dưới `models/latest/model.pkl`.
