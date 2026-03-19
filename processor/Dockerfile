FROM python:3.11-alpine

WORKDIR /app

# Install build dependencies for psycopg (requires pg_config / libpq)
RUN apk add --no-cache \
    gcc \
    musl-dev \
    postgresql-dev \
    ca-certificates

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY processor.py ./processor.py

CMD ["python", "-u", "processor.py"]