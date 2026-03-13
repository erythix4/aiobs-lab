FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# ARG force le cache-bust sur chaque rebuild
ARG CACHEBUST=1
COPY main.py .
HEALTHCHECK --interval=5s --timeout=3s --retries=12 --start-period=15s \
    CMD curl -sf http://localhost:8000/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
