FROM python:3.11-slim

ENV TZ=Asia/Jakarta

# System deps needed by mediapipe's bundled OpenCV and scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=1000 "numpy>=1.23,<2" "scipy>=1.10,<1.12" && \
    pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

COPY backend/ ./backend
COPY frontend/ ./frontend

WORKDIR /app/backend

RUN mkdir -p /app/database

EXPOSE 5000

ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
