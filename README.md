# Pristmax

**Less storage. More clarity.**

[![CI](https://github.com/chunchengzheng58-ctrl/pristmax/actions/workflows/ci.yml/badge.svg)](https://github.com/chunchengzheng58-ctrl/pristmax/actions)
[![Release](https://img.shields.io/github/v/release/chunchengzheng58-ctrl/pristmax?include_prereleases)](https://github.com/chunchengzheng58-ctrl/pristmax/releases)
[![License](https://img.shields.io/github/license/chunchengzheng58-ctrl/pristmax)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

Enterprise data storage optimization — runs locally, verifies integrity, reduces footprint.

[Website](https://jiangchenghehe.top) · [Docs](src/pristmax/site/docs.html) · [Changelog](CHANGELOG.md)

---

## Features

| Feature | Description |
|---------|-------------|
| 📊 **Storage Analysis** | Scan and categorize files by type, size, and location |
| 🔄 **Deduplication** | Find and remove duplicate files to save space |
| 📦 **Large File Detection** | Identify space-hogging files |
| 🤖 **AI Integration (MCP)** | Use with Claude Code, Cursor via Model Context Protocol |
| 🌐 **REST API** | Integrate with other systems |
| 📱 **Web Console** | User-friendly management UI |

---

## Quick Start

### Install

```bash
# Clone the repository
git clone https://github.com/chunchengzheng58-ctrl/pristmax.git
cd pristmax

# Install dependencies
pip install flask flask-cors pyyaml

# Run
python main.py --host 0.0.0.0 --port 5000
```

Open http://localhost:5000

### Storage Agent CLI

```bash
# Analyze directory
python -m src.pristmax.agent.cli --path /data --analyze

# Find large files
python -m src.pristmax.agent.cli --large-files --min 100

# Find duplicates
python -m src.pristmax.agent.cli --duplicates

# Get statistics
python -m src.pristmax.agent.cli --stats

# Natural language chat
python -m src.pristmax.agent.cli --chat

# Start API server
python -m src.pristmax.agent.cli --serve --port 5002
```

---

## AI Integration (MCP)

Storage Agent supports [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) for AI assistant integration.

### Claude Code Setup

Edit `~/.claude/settings.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "storage-agent": {
      "command": "python",
      "args": ["-m", "src.pristmax.agent.mcp_server"],
      "cwd": "/path/to/pristmax"
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `storage_stats` | Get directory statistics |
| `storage_large_files` | Find large files |
| `storage_duplicates` | Find duplicate files |
| `storage_suggestions` | Get optimization suggestions |
| `storage_analyze` | Comprehensive analysis |
| `storage_chat` | Natural language Q&A |
| `storage_cleanup_duplicates` | Cleanup duplicates (dry-run) |
| `storage_cleanup_large` | Cleanup large files (dry-run) |

See [mcp/README.md](mcp/README.md) for full documentation.

---

## Architecture

```
pristmax/
├── src/pristmax/        ← Open source core (Apache 2.0)
│   ├── api/            REST API server
│   ├── web/            Product console UI
│   ├── scheduler/      Task scheduling & queue
│   ├── storage/        Storage abstraction layer
│   ├── auth/           Authentication & RBAC
│   ├── monitor/        System metrics & alerts
│   └── agent/          Storage Agent CLI & MCP
├── site/               Marketing website
├── mcp/                MCP Server documentation
├── commercial/          ← Proprietary (separate license)
│   ├── encoder/        H.265 video encoding
│   └── surveillance/   Video analysis
└── main.py             Application entry point
```

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

## Open Source Philosophy

**Commercial parts are not open source.**

| Category | Status |
|----------|--------|
| Open source core (Apache 2.0) | ✅ Public on GitHub |
| Proprietary components | 🔒 Not public, separate license |

---

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) and [Security Policy](SECURITY.md).

---

## License

Open source components: Apache 2.0

Proprietary components (H.265 encoder, video analysis): [Contact for licensing](mailto:[pending])

---

## Contact

- Website: https://jiangchenghehe.top
- GitHub: https://github.com/chunchengzheng58-ctrl/pristmax
- Issues: [GitHub Issues](https://github.com/chunchengzheng58-ctrl/pristmax/issues)
