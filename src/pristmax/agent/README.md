# Storage Agent

**智能存储管家 - 企业级存储优化工具 (v2.0)**

A CLI tool and MCP server for analyzing storage, finding duplicates, and optimizing disk usage.

## Features

### Core Features
- 📊 **Statistics** - 存储统计，支持并行扫描
- 🔄 **Deduplication** - 快速哈希 + 精确验证查重
- 📦 **Large Files** - 分页查找大文件
- 💡 **Smart Suggestions** - AI 优化建议
- 🔍 **Content Search** - 文件内容正则搜索
- 👁 **File Monitoring** - 实时文件变化监控

### Advanced Features
- ⏰ **Scheduled Tasks** - Cron 定时扫描 (APScheduler)
- ☁️ **Cloud Storage** - S3/OSS/MinIO 集成
- 🔄 **Desktop Sync** - 本地 + 云端同步
- 📋 **Health Check** - 系统健康检查
- 💾 **SQLite Cache** - TTL 缓存加速

### Integration
- 🤖 **MCP Server** - Claude Code, Cursor 等 MCP 客户端
- 🌐 **REST API** - HTTP 接口
- 📱 **Desktop App** - Electron 桌面应用

## Installation

```bash
# From source
git clone https://github.com/chunchengzheng58-ctrl/pristmax.git
cd pristmax
pip install -e .
```

### Dependencies

```bash
pip install flask flask-cors pyyaml watchdog apscheduler boto3
```

## CLI Usage

```bash
# Analyze a directory
python -m src.pristmax.agent.cli --path /data --analyze

# Get statistics with progress bar
python -m src.pristmax.agent.cli --stats --path /data

# Find files larger than 100MB
python -m src.pristmax.agent.cli --large-files --min 100

# Find duplicate files (fast hash + verification)
python -m src.pristmax.agent.cli --duplicates

# Search file content with regex
python -m src.pristmax.agent.cli --search "password" --path /data

# Monitor directory changes
python -m src.pristmax.agent.cli --monitor --path /data

# Export HTML/JSON/CSV report
python -m src.pristmax.agent.cli --export --path /data --format html -o report.html

# Cleanup duplicates (preview mode)
python -m src.pristmax.agent.cli --cleanup --path /data --type duplicates
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

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `storage_stats` | 获取目录存储统计 |
| `storage_large_files` | 查找大文件 |
| `storage_duplicates` | 查找重复文件 |
| `storage_search_content` | 搜索文件内容 |
| `storage_monitor_start` | 启动文件监控 |
| `storage_schedule_add` | 添加定时任务 |
| `storage_cloud_config` | 配置云存储 |
| `storage_sync_save` | 保存扫描结果 |
| `storage_health` | 健康检查 |
| `storage_cache_stats` | 缓存统计 |

## API Server

```bash
python -m src.pristmax.agent.api_server --port 5000
```

## Performance

- **Parallel Scanning** - ThreadPoolExecutor 并行处理
- **Fast Hash** - 快速哈希 (前后1MB + 大小)
- **Generator** - 生成器迭代减少内存
- **SQLite Cache** - TTL 缓存避免重复扫描
- **frozenset** - 文件类型映射 O(1) 查找

## Security

- 路径白名单控制
- 路径遍历检查
- 符号链接检测
- 只读模式
- 操作审批流程
- 完整审计日志

## License

Apache 2.0
