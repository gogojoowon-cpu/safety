# family-guardian web demo image.
# 브라우저가 카메라 프레임을 POST 하면 서버가 분석 → JSON 으로 회신.

FROM python:3.11-slim

# OpenCV + MediaPipe 가 의존하는 X11 / GL / image libs (headless 도 일부 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Railway 가 $PORT 를 주입한다. 로컬에서 그냥 띄울 땐 8000.
CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
