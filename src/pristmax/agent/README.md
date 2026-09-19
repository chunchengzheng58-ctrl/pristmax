# Storage Agent

**Intelligent storage analysis and optimization tool.**

A CLI tool and MCP server for analyzing storage, finding duplicates, and optimizing disk usage.

## Features

- 📊 **Statistics**: Get detailed storage breakdown by file type
- 🔄 **Deduplication**: Find and remove duplicate files
- 📦 **Large Files**: Identify space-hogging files
- 💡 **Smart Suggestions**: AI-powered optimization recommendations
- 💬 **Natural Language**: Chat with your storage in plain English
- 🔍 **Incremental Scan**: Fast re-scans with SQLite cache
- 🤖 **MCP Server**: Integrates with Claude Code, Cursor, etc.

## Installation

```bash
# From source
git clone https://github.com/chunchengzheng58-ctrl/pristmax.git
cd pristmax
pip install flask flask-cors pyyaml
```

## CLI Usage

```bash
# Analyze a directory
python -m src.pristmax.agent.cli --path /data --analyze

# Get statistics with progress bar
python -m src.pristmax.agent.cli --stats --path /data

# Find files larger than 100MB
python -m src.pristmax.agent.cli --large-files --min 100

# Find duplicate files
python -m src.pristmax.agent.cli --duplicates

# Get optimization suggestions
python -m src.pristmax.agent.cli --suggest --path /data

# Natural language chat mode
python -m src.pristmax.agent.cli --chat --path /data

# Monitor directory changes
python -m src.pristmax.agent.cli --monitor --path /data --interval 30

# Export HTML report
python -m src.pristmax.agent.cli --export --path /data --format html -o report.html

# Cleanup duplicates (preview mode)
python -m src.pristmax.agent.cli --cleanup-duplicates --path /data

# Cleanup duplicates (execute)
python -m src.pristmax.agent.cli --cleanup-duplicates --path /data --execute

# Cleanup large files
python -m src.pristmax.agent.cli --cleanup-large --path /data --min 500 --execute
```

## MCP Server

### Claude Code Integration

Add to your `settings.json`:

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
| `storage_stats` | Directory statistics |
| `storage_large_files` | Find large files |
| `storage_duplicates` | Find duplicates |
| `storage_suggestions` | Get recommendations |
| `storage_analyze` | Full analysis |
| `storage_chat` | Natural language Q&A |
| `storage_cleanup_duplicates` | Preview/execute cleanup |
| `storage_cleanup_large` | Preview/execute cleanup |

### HTTP Mode

```bash
python -m src.pristmax.agent.mcp_server --mode http --port 5003
```

## Examples

### Analyze Home Directory

```bash
python -m src.pristmax.agent.cli --stats --path ~
```

Output:
```
📈 存储统计: /Users/me
==================================================
✅ 扫描完成 1,247 文件

【概览】
   总文件数: 1,247
   总大小:   45.2 GB

【类型分布】
   视频       [████████████████████] 28.5 GB
   图片       [██████████          ] 12.1 GB
   代码       [████                ]  3.2 GB
   文档       [██                  ]  1.4 GB
```

### Find Large Files

```bash
python -m src.pristmax.agent.cli --large-files --min 1000 --path /data
```

### Natural Language Query

```bash
python -m src.pristmax.agent.cli --chat --path /data
# Bot: Storage Agent 对话模式
# Bot: 输入 'quit' 退出

你: 哪些文件夹占用空间最大
Bot: 根据分析，以下文件夹占用空间最大：
     1. /data/videos - 128.5 GB
     2. /data/photos - 45.2 GB
     3. /data/downloads - 12.8 GB
```

## License

Apache 2.0 - See [LICENSE](../../LICENSE)
