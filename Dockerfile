FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install "bcrypt<4.0.0" 
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/output /data/checkpoints

ENV PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/data/output \
    API_BASE=http://localhost:8000/api

EXPOSE 7860 8000

CMD ["python", "ui/app.py"]
