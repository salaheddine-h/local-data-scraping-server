# 🖥️ local-data-scraping-server

> A scalable, Docker-based backend system for asynchronous web scraping and data processing using a queue-based architecture.

## 🚀 Why this project matters

This project simulates a real-world backend data pipeline used in production systems. It demonstrates how to design scalable, asynchronous architectures for handling large volumes of scraping tasks using queue-based processing and containerized services.

It reflects concepts used in modern backend and DevOps environments such as microservices, message queues, and distributed workers.

![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-009639?style=flat&logo=nginx&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 🌍 Status

- ✅ Local environment ready
- 🚧 Deployment in progress

## 🖼️ Preview

![Architecture](./docs/architecture.png)

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Technologies](#-technologies)
- [Project Structure](#-project-structure)
- [How It Works](#-how-it-works)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Running the System](#-running-the-system)
- [API Usage](#-api-usage)
- [Scaling Workers](#-scaling-workers)
- [Example Requests](#-example-requests)
- [Future Improvements](#-future-improvements)
- [License](#-license)

---

## 📖 Overview

**local-data-scraping-server** is a fully local, Docker-orchestrated backend platform that lets you:

- Submit scraping jobs through a REST API
- Process multiple URLs concurrently using async Python workers
- Clean and normalize raw scraped data through a pipeline processor
- Store structured datasets in a PostgreSQL database
- Query stored data at any time via the API

The entire stack starts with a single command and runs without any cloud dependency.

---

## 🏗️ Architecture

```
                          ┌────────────────────────────────────────────┐
                          │            Local Machine (Your PC)          │
                          │                                            │
  Browser / curl / PS ──► │  ┌─────────────────────────────────────┐  │
                          │  │        Nginx  (port 8080)            │  │
                          │  │        Reverse Proxy                 │  │
                          │  └─────────────┬───────────────────────┘  │
                          │                │                            │
                          │  ┌─────────────▼───────────────────────┐  │
                          │  │       FastAPI  (port 8000)           │  │
                          │  │       REST API (POST/GET endpoints)  │  │
                          │  └──────┬──────────────────┬────────────┘  │
                          │         │ RPUSH tasks       │ DB queries    │
                          │  ┌──────▼──────┐    ┌──────▼──────────┐   │
                          │  │    Redis    │    │   PostgreSQL    │   │
                          │  │  Task Queue │    │   datasets DB   │   │
                          │  └──────┬──────┘    └──────▲──────────┘   │
                          │         │ BLPOP              │ INSERT rows  │
                          │  ┌──────▼──────────────┐    │             │
                          │  │  Scraper Workers     │    │             │
                          │  │  (aiohttp / asyncio) │    │             │
                          │  └──────┬───────────────┘    │             │
                          │         │ RPUSH results        │             │
                          │  ┌──────▼──────────────┐     │             │
                          │  │  Processor Service   ├─────┘             │
                          │  │  (clean + structure) │                   │
                          │  └─────────────────────┘                   │
                          └────────────────────────────────────────────┘
```

---

## 🛠️ Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Reverse Proxy | **Nginx 1.27** | Routes all external HTTP traffic to the API |
| REST API | **FastAPI + Uvicorn** | Accepts tasks, returns datasets and health status |
| Task Queue | **Redis 7** | Decouples the API from workers via RPUSH/BLPOP lists |
| Scraper Workers | **Python + aiohttp** | Fetch URLs concurrently with async I/O |
| Data Processor | **Python + psycopg 3** | Cleans raw payloads and persists to PostgreSQL |
| Database | **PostgreSQL 16** | Stores normalized dataset records |
| Orchestration | **Docker Compose** | Wires all services together in one command |

---

## 📁 Project Structure

```
local-data-scraping-server/
│
├── docker-compose.yml          # Service orchestration
├── .env.example                # Environment variable template
├── .gitignore
│
├── api/                        # FastAPI application
│   ├── Dockerfile
│   ├── main.py                 # POST /task  GET /datasets  GET /status
│   └── requirements.txt
│
├── workers/                    # Async scraper worker
│   ├── Dockerfile
│   ├── worker.py               # aiohttp-based async fetcher
│   └── requirements.txt
│
├── processor/                  # Data cleaning & persistence
│   ├── Dockerfile
│   ├── processor.py            # Normalizes raw data, writes to PostgreSQL
│   └── requirements.txt
│
├── nginx/
│   └── default.conf            # Proxy rules
│
├── database/
│   └── init.sql                # Schema: datasets table + indexes
│
└── scripts/
    ├── add_task.ps1            # PowerShell helper to submit a task
    └── add_task.sh             # Bash helper to submit a task
```

---

## ⚙️ How It Works

The system follows a simple, linear pipeline:

```
POST /task
    │
    ▼
FastAPI  ──RPUSH──►  Redis (scrape_tasks queue)
                          │
                          │ BLPOP
                          ▼
                   Scraper Worker
                   (aiohttp fetch – runs N concurrent jobs)
                          │
                          │ RPUSH
                          ▼
                   Redis (processing_tasks queue)
                          │
                          │ BLPOP
                          ▼
                   Processor Service
                   (clean, normalize, extract fields)
                          │
                          │ INSERT
                          ▼
                   PostgreSQL  ──►  GET /datasets
```

1. **API** receives a `POST /task` request and pushes a JSON job onto the `scrape_tasks` Redis list.
2. **Scraper workers** block-pop jobs from Redis, fetch the target URL with `aiohttp`, and push raw results onto the `processing_tasks` queue. Multiple jobs run concurrently inside a single worker process via `asyncio`.
3. **Processor** block-pops raw results, normalises the payload (HTML stripping, field extraction, whitespace cleanup), and inserts clean records into the `datasets` table in PostgreSQL.
4. **API** `GET /datasets` reads from PostgreSQL and returns the structured results.

---

## ✅ Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with WSL 2 backend on Windows) or Docker Engine on Linux/macOS
- `docker compose` v2 (`docker compose version`)
- No Python installation needed locally — everything runs inside containers

---

## 🚀 Installation

```bash
# 1. Clone the repository
git clone https://github.com/salaheddine-h/local-data-scraping-server.git
cd local-data-scraping-server

# 2. Copy the environment template
cp .env.example .env
# Edit .env if you want to change passwords or queue names (optional)
```

---

## ▶️ Running the System

### Start everything with one command

```bash
docker compose up --build -d
```

This pulls base images, builds the three Python service images, creates the network and the `pgdata` volume, and starts all six containers.

### Verify all containers are healthy

```bash
docker compose ps
```

Expected output:

```
NAME                       STATUS
project-nginx-1            Up
project-api-1              Up (healthy)
project-redis-1            Up (healthy)
project-postgres-1         Up (healthy)
project-scraper-worker-1   Up
project-processor-1        Up
```

### Check the health endpoint

```bash
curl http://localhost:8080/status
```

```json
{
  "service": "api",
  "overall": "ok",
  "redis": { "status": "ok", "scrape_queue_length": 0, "processing_queue_length": 0 },
  "postgres": { "status": "ok", "dataset_count": 0 }
}
```

### Stop the stack

```bash
docker compose down
```

To also delete the stored database volume:

```bash
docker compose down -v
```

---

## 📡 API Usage

The API is exposed through Nginx at `http://localhost:8080`.

### `POST /task` — Submit a scraping task

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string (URL) | ✅ | The URL to scrape |
| `source` | string | ❌ | Logical source label (default: `"manual"`) |
| `metadata` | object | ❌ | Arbitrary key-value pairs attached to the task |
| `request_timeout` | integer (1–120) | ❌ | HTTP timeout in seconds (default: `20`) |

### `GET /datasets` — Query stored records

| Query param | Type | Description |
|-------------|------|-------------|
| `limit` | integer (1–500) | Max records to return (default: `50`) |
| `source` | string | Filter by source label |
| `status` | string | Filter by status (`processed` / `failed`) |

### `GET /status` — System health

Returns live status for the API, Redis (with queue depths), and PostgreSQL (with dataset count).

---

## 📬 Example Requests

### Using `curl` (Linux / macOS / WSL)

```bash
# Submit a task
curl -X POST http://localhost:8080/task \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://jsonplaceholder.typicode.com/posts",
    "source": "jsonplaceholder",
    "metadata": { "requested_by": "demo" }
  }'

# Fetch stored datasets
curl "http://localhost:8080/datasets?limit=5&source=jsonplaceholder"

# Check system health
curl http://localhost:8080/status
```

### Using PowerShell (Windows)

```powershell
# Submit a task using the helper script
./scripts/add_task.ps1 -Url "https://jsonplaceholder.typicode.com/posts" -Source "jsonplaceholder"

# Or manually
$body = @{
    url    = "https://jsonplaceholder.typicode.com/posts"
    source = "jsonplaceholder"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:8080/task" `
    -ContentType "application/json" -Body $body

# Fetch datasets
Invoke-RestMethod "http://localhost:8080/datasets?limit=5" | ConvertTo-Json -Depth 5

# Health check
Invoke-RestMethod "http://localhost:8080/status" | ConvertTo-Json -Depth 5
```

### Example `POST /task` response

```json
{
  "status": "queued",
  "queue": "scrape_tasks",
  "task": {
    "task_id": "d0e6ae0f-3feb-44b7-bc1e-a6ba592981a2",
    "url": "https://jsonplaceholder.typicode.com/posts",
    "source": "jsonplaceholder",
    "submitted_at": "2026-03-16T18:48:57.176544+00:00"
  }
}
```

### Example `GET /datasets` response

```json
{
  "count": 3,
  "items": [
    {
      "id": 1,
      "task_id": "d0e6ae0f-3feb-44b7-bc1e-a6ba592981a2",
      "source": "jsonplaceholder",
      "url": "https://jsonplaceholder.typicode.com/posts",
      "title": "sunt aut facere repellat provident occaecati",
      "content": "quia et suscipit suscipit recusandae consequuntur...",
      "status": "processed",
      "created_at": "2026-03-16T18:48:57.688824Z"
    }
  ]
}
```

---

## 📈 Scaling Workers

Workers are stateless — you can run as many as your machine can handle. All workers share the same Redis queue and pick up jobs independently.

```bash
# Run 3 parallel worker containers
docker compose up -d --scale scraper-worker=3

# Run 5 parallel worker containers
docker compose up -d --scale scraper-worker=5
```

Each worker also runs `WORKER_CONCURRENCY` (default: 5) async jobs internally, so 3 containers × 5 concurrent fetches = **15 simultaneous HTTP requests**.

To change the internal concurrency without scaling containers, set the env variable in `.env`:

```env
WORKER_CONCURRENCY=10
```

Then restart the worker:

```bash
docker compose up -d --no-deps --build scraper-worker
```

---

## 🔮 Future Improvements

| Feature | Description |
|---------|-------------|
| **Redis Streams / Celery** | Replace simple list queues with durable, acknowledgement-backed message delivery |
| **Retry + dead-letter queue** | Automatically retry failed scrape jobs and route persistent failures to a DLQ |
| **Site-specific parsers** | Plug-in parser modules per domain for structured field extraction (price, date, author, etc.) |
| **Scheduler** | Cron-style recurring tasks — scrape a source every hour without manual API calls |
| **Web dashboard** | Real-time job monitor and dataset browser (e.g. Streamlit or a lightweight React UI) |
| **Rate limiting** | Per-domain request throttling to respect `robots.txt` and avoid IP bans |
| **Authentication** | API key or JWT-based auth to protect the `/task` endpoint |
| **Prometheus + Grafana** | Metrics scraping and dashboards for queue depth, worker throughput, and error rates |
| **Export endpoints** | `GET /datasets/export?format=csv` and `GET /datasets/export?format=jsonl` |
| **Distributed deployment** | Docker Swarm or k3s manifest for spreading workers across multiple machines |

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<p align="center">Built for local experimentation, learning, and personal data projects.</p>
