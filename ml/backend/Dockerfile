FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AEGIS_PLATFORM_MODEL_DIR=/app/ml_artifacts/platforms \
    MIN_MODEL_COVERAGE_FRACTION=0.995

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY ml_artifacts ./ml_artifacts

EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
