# Pristmax Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Users                                │
│  (Web UI / CLI / API / AI Assistants via MCP)              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                      API Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐    │
│  │ Auth API   │  │ Stats API   │  │ Task API (SSE)  │    │
│  └─────────────┘  └─────────────┘  └─────────────────┘    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   Service Layer                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐    │
│  │ Scheduler   │  │ Monitor     │  │ Storage Agent   │    │
│  │             │  │             │  │ (CLI + MCP)    │    │
│  └─────────────┘  └─────────────┘  └─────────────────┘    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  Storage Backends                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────┐  │
│  │ Local   │  │ NAS     │  │ Cloud   │  │ RAID        │  │
│  │ Disk    │  │ SMB/NFS │  │ S3/OSS  │  │             │  │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. API Layer (`src/pristmax/api/`)

RESTful API server built with Flask.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | User authentication |
| `/api/auth/register` | POST | User registration |
| `/api/stats` | GET | System statistics |
| `/api/tasks` | GET/POST | Task management |
| `/api/tasks/<id>/stream` | GET | SSE progress streaming |
| `/api/storages` | GET | List storage volumes |
| `/health` | GET | Health check |

### 2. Storage Agent (`src/pristmax/agent/`)

Command-line tool and MCP server for storage analysis.

```
storage-agent/
├── cli.py          # CLI interface
├── storage_agent.py # Core analysis engine
├── mcp_server.py  # MCP protocol server
└── api.py         # REST API integration
```

### 3. Storage Backends (`src/pristmax/storage/`)

Abstraction layer for multiple storage types.

```
storage/
├── adapters/
│   ├── local.py     # Local filesystem
│   ├── nas.py       # SMB/NFS mounts
│   ├── s3.py        # AWS S3 / compatible
│   └── oss.py       # Aliyun OSS
└── manager.py       # Unified interface
```

### 4. Web Console (`src/pristmax/web/`)

Admin dashboard for system management.

### 5. Scheduler (`src/pristmax/scheduler/`)

Background task scheduling with queue support.

## Data Flow

### Storage Analysis Flow

```
User Command → CLI/MCP → StorageAgent → Storage Backend
                                    │
                                    ▼
                              SQLite Cache
                                    │
                                    ▼
                              Results/Report
```

### Task Processing Flow

```
API Request → Task Queue → Scheduler → Worker → Result
                                    │
                                    ▼
                              SSE Stream → Client
```

## Deployment Options

### 1. Single Server

```
┌─────────────────────┐
│   Web Server        │
│   ┌───────────────┐ │
│   │ Flask + Nginx │ │
│   └───────────────┘ │
└─────────────────────┘
```

### 2. Distributed

```
                    ┌─────────────┐
                    │ Load        │
                    │ Balancer    │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
   ┌───────────┐    ┌───────────┐    ┌───────────┐
   │ Worker 1  │    │ Worker 2  │    │ Worker N  │
   └───────────┘    └───────────┘    └───────────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           ▼
                    ┌─────────────┐
                    │ Redis Queue │
                    └─────────────┘
```

## Technology Stack

| Layer | Technology |
|-------|------------|
| Web Framework | Flask 3.0+ |
| Database | SQLite |
| Task Queue | In-memory (simple) / Redis (production) |
| Frontend | Vanilla JS + CSS |
| CLI | Python argparse |
| Protocol | MCP (Model Context Protocol) |
| Deployment | Docker, systemd, nginx |
