FROM python:3.11-alpine

WORKDIR /app

RUN apk update && apk add --no-cache \
	build-base \
	libffi-dev \
	openssl-dev \
	ca-certificates

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
	pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]