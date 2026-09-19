# Pristmax

**Less storage. More clarity.**

Enterprise data storage optimization — runs locally, verifies integrity, reduces footprint.

Built with Claude Code by Anthropic · [Website](https://jiangchenghehe.top) · [Docs](src/pristmax/site/docs.html)

---

## AI Integration (MCP)

Storage Agent 支持 MCP (Model Context Protocol)，可被 Claude Code、Cursor 等 AI 助手直接调用。

```bash
# 配置 Claude Desktop
# 编辑 ~/.claude/settings.json (macOS) 或 %APPDATA%\Claude\claude_desktop_config.json (Windows)
{
  "mcpServers": {
    "storage-agent": {
      "command": "python",
      "args": ["-m", "src.pristmax.agent.mcp_server"],
      "cwd": "你的项目路径"
    }
  }
}
```

可用工具：`storage_stats`、`storage_large_files`、`storage_duplicates`、`storage_suggestions`、`storage_chat` 等。

详细文档：[mcp/README.md](mcp/README.md)

---

## Open Source Philosophy

**Commercial parts are not open source.**

Pristmax follows a clear boundary between open source and proprietary:

| Category | Status |
|----------|--------|
| Open source core (Apache 2.0) | ✅ Public on GitHub |
| Proprietary components | 🔒 Not public, separate license |

This means:
- Core storage optimization technology is open and transparent
- Advanced features (video encoding, AI analysis) remain proprietary
- You can inspect, modify, and use the open source parts freely

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
