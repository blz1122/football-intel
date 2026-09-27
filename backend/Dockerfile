# ---- Football Intelligence API · FastAPI 后端镜像 ----
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 系统依赖（xgboost/scikit-learn 无需额外编译；numpy 用 wheel）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY run.py .

# 模型缓存与 SQLite（mock 模式）目录
RUN mkdir -p ml_models

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -sf http://127.0.0.1:8000/api/v1/health || exit 1

# run.py 固定使用 websockets-sansio（uvicorn 0.5x lifespan 任务丢帧规避，见 README）
CMD ["python", "run.py", "8000", "0.0.0.0"]
