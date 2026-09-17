# Pristmax

**Less storage. More clarity.**

Pristmax is an enterprise data storage optimization system that reduces redundancy, verifies integrity, and manages storage — running entirely in your own environment.

[Website](https://jiangchenghehe.top) · [Docs](site/docs.html) · [Download](#download)

---

## Features

### Understand Your Data
Scan directories to establish baselines on capacity, duplication rate, and access frequency.

### Reduce Storage Footprint
- **Deduplication**: Content-defined chunking (FastCDC) identifies duplicate data blocks
- **Video Optimization**: H.265 encoding with configurable quality modes — lossless, visually lossless, or compressed backup
- **Semantic Reduction**: ROI detection, background separation for video content

### Verify Results
- Lossless paths validate file hashes after restore
- Video quality metrics for lossy paths

### Stay in Control
- All processing runs locally in your environment — no data leaves your infrastructure
- Multi-backend storage: Local disk, NAS, USB, Cloud, RAID
- Real-time task monitoring with SSE streaming
- RESTful API for integration

---

## Quick Start

### Download
Get the latest release from [GitHub Releases](https://github.com/chunchengzheng58-ctrl/pristmax/releases).

### Run
```
./Pristmax.exe --host 0.0.0.0 --port 5000
```
Then open http://localhost:5000 in your browser.

### From Source
```bash
pip install -r unified/requirements.txt
python main.py --host 0.0.0.0 --port 5000
```

---

## Architecture

```
Pristmax
├── Web UI          # Local browser-based console
├── API Server      # Flask REST API (port 5000)
├── Task Scheduler  # Background job queue (ThreadPoolExecutor)
├── Storage Layer   # Unified adapter: Local / NAS / USB / Cloud / RAID
├── Encoder         # H.265 video encoding
└── Dedup Engine    # FastCDC content-defined chunking
```

---

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Login |
| `/api/auth/register` | POST | Register |
| `/api/stats` | GET | System statistics |
| `/api/tasks` | GET/POST | List or create tasks |
| `/api/tasks/<id>/stream` | GET | SSE task progress |
| `/api/storages` | GET | List storage volumes |

Full API documentation at `/api/docs` (Swagger UI).

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

Coming soon. Contact the team for details.

---

## Contact

- Website: https://jiangchenghehe.top
- GitHub Issues: https://github.com/chunchengzheng58-ctrl/pristmax/issues
