FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn numpy scikit-learn pydantic

COPY . .

WORKDIR /app/backend
EXPOSE 8001

CMD ["python", "-m", "uvicorn", "mock_ml_service:app", "--host", "0.0.0.0", "--port", "8001"]

