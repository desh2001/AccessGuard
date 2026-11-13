FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY collector.py .
RUN useradd -r -u 10002 appuser
USER appuser
EXPOSE 5514
CMD ["python", "-u", "collector.py"]
