# family-guardian web demo — repo-root Dockerfile.
# Railway/Render 등에서 별도 "Root Directory" 설정 없이 그대로 빌드되도록,
# 루트에서 family-guardian/ 를 COPY 한다.

FROM python:3.11-slim

# OpenCV + MediaPipe 가 의존하는 X11 / GL / image libs
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

# requirements 만 먼저 복사해서 캐시 효율 확보
COPY family-guardian/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 나머지 앱 코드
COPY family-guardian/ ./

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
