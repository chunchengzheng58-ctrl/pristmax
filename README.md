# Pristmax

**Less storage. More clarity.**

Enterprise data storage optimization — runs locally, verifies integrity, reduces footprint.

Built with Claude Code by Anthropic · [Website](https://jiangchenghehe.top) · [Docs](src/pristmax/site/docs.html)

---

## Project Structure

```
pristmax/
├── src/pristmax/        ← Open source core (Apache 2.0)
│   ├── api/            REST API server
│   ├── web/            Product console UI
│   ├── scheduler/      Task scheduling & queue
│   ├── storage/        Storage abstraction layer
│   ├── auth/           Authentication & RBAC
│   ├── monitor/        System metrics & alerts
│   └── site/           Marketing website
├── commercial/          ← Proprietary (separate license)
│   ├── encoder/        H.265 video encoding
│   └── surveillance/   ROI/ASVC/BLUE video analysis
├── binaries/           Windows executables (downloads)
├── docs/              Architecture docs
├── main.py            Application entry point
└── main.spec          PyInstaller packaging config
```

---

## Quick Start

### Run the application
```bash
pip install -r src/pristmax/requirements.txt
python main.py --host 0.0.0.0 --port 5000
```
Open http://localhost:5000

### Download executable
Get `binaries/Pristmax.exe` from [Releases](https://github.com/chunchengzheng58-ctrl/pristmax/releases).

---

## Features

| Feature | Module | License |
|---------|--------|---------|
| REST API | `src/pristmax/api/` | Open Source |
| Task Scheduler | `src/pristmax/scheduler/` | Open Source |
| Storage Adapters | `src/pristmax/storage/` | Open Source |
| Web Console | `src/pristmax/web/` | Open Source |
| Marketing Site | `src/pristmax/site/` | Open Source |
| H.265 Encoding | `commercial/encoder/` | Proprietary |
| Video Analysis | `commercial/surveillance/` | Proprietary |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Login |
| `/api/auth/register` | POST | Register |
| `/api/stats` | GET | System statistics |
| `/api/tasks` | GET/POST | List or create tasks |
| `/api/tasks/<id>/stream` | GET | SSE task progress |
| `/api/storages` | GET | List storage volumes |
| `/health` | GET | Health check |

---

## Storage Backends

| Type | Status |
|------|--------|
| Local Disk | ✅ |
| NAS (SMB/NFS) | ✅ |
| USB Drive | ✅ |
| Cloud (S3/OSS/COS) | ✅ |
| RAID | ✅ |

---

## License

Open source components: Apache 2.0

Proprietary components (H.265 encoder, video analysis): [Contact for licensing](mailto:[pending])

---

## Contact

- Website: https://jiangchenghehe.top
- GitHub: https://github.com/chunchengzheng58-ctrl/pristmax
