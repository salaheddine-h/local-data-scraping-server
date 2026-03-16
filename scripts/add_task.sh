#!/usr/bin/env sh

URL="${1:-https://jsonplaceholder.typicode.com/posts}"
SOURCE="${2:-jsonplaceholder}"

curl -X POST http://localhost:8080/task \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"${URL}\",\"source\":\"${SOURCE}\"}"