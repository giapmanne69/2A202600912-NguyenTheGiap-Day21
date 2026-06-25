from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import boto3
import joblib
import os

app = FastAPI()

# Đọc cấu hình từ biến môi trường
AWS_BUCKET = os.environ.get("AWS_BUCKET", os.environ.get("GCS_BUCKET"))
AWS_MODEL_KEY = "models/latest/model.pkl"
MODEL_PATH = os.path.expanduser("~/models/model.pkl")


def download_model():
    """Tải file model.pkl từ S3 về máy khi server khởi động."""
    # Tạo thư mục chứa model nếu chưa tồn tại
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    
    # TODO 2.6.1: Tạo boto3 s3 client
    s3 = boto3.client('s3')
    
    # TODO 2.6.2: Gọi s3.download_file(AWS_BUCKET, AWS_MODEL_KEY, MODEL_PATH)
    s3.download_file(AWS_BUCKET, AWS_MODEL_KEY, MODEL_PATH)
    
    # TODO 2.6.3: In thông báo thành công
    print("Model đã được tải xuống từ S3.")


# Gọi hàm này khi module được import (chạy khi server khởi động)
# Thêm kiểm tra môi trường để tránh lỗi khi chạy pytest cục bộ
if os.environ.get("TESTING") != "True":
    download_model()
    model = joblib.load(MODEL_PATH)
else:
    model = None


class PredictRequest(BaseModel):
    features: list[float]


@app.get("/health")
def health():
    """Endpoint kiểm tra sức khỏe server. GitHub Actions dùng endpoint này để xác nhận deploy thành công."""
    # TODO 2.6.4: Trả về dict {"status": "ok"}
    return {"status": "ok"}


@app.post("/predict")
def predict(req: PredictRequest):
    """
    Endpoint suy luận.

    Đầu vào: JSON {"features": [f1, f2, ..., f12]}
    Đầu ra:  JSON {"prediction": <0|1|2>, "label": <"thấp"|"trung_bình"|"cao">}
    """
    # TODO 2.6.5: Kiểm tra len(req.features) == 12.
    if len(req.features) != 12:
        raise HTTPException(status_code=400, detail="Expected 12 features (wine quality)")

    # TODO 2.6.6: Gọi model.predict([req.features]) để lấy kết quả dự đoán.
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")
    pred = int(model.predict([req.features])[0])

    # TODO 2.6.7: Trả về dict chứa "prediction" (int) và "label" (string).
    #   Nhãn: 0 -> "thấp", 1 -> "trung_bình", 2 -> "cao"
    labels = {0: "thấp", 1: "trung_bình", 2: "cao"}
    label = labels.get(pred, "không xác định")
    return {"prediction": pred, "label": label}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
