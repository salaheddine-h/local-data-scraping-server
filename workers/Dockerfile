FROM python:3.11-alpine

WORKDIR /app

# Install build dependencies for requests, beautifulsoup4, etc.
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    ca-certificates

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY worker.py ./worker.py
COPY scraper.py ./scraper.py
COPY redis_queue.py ./redis_queue.py

CMD ["python", "-u", "worker.py"]