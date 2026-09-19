# Storage Agent MCP Server

MCP (Model Context Protocol) 服务器，让 AI 助手直接调用 Storage Agent。

## 支持的 AI

| AI 产品 | 支持状态 |
|---------|---------|
| Claude Code | ✅ 已验证 |
| Cursor | ✅ 兼容 |
| 其他 MCP 客户端 | ✅ 通用 |

## 快速接入

### 1. Claude Code

编辑 `~/.claude/settings.json`（macOS）或 `%APPDATA%\Claude\claude_desktop_config.json`（Windows）：

```json
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

### 2. Cursor

在 Cursor 设置中找到 MCP 配置，添加同样的配置。

## 可用工具

| 工具 | 说明 |
|------|------|
| `storage_stats` | 获取目录统计（文件数、大小、分类） |
| `storage_large_files` | 查找大文件 |
| `storage_duplicates` | 查找重复文件 |
| `storage_suggestions` | 获取优化建议 |
| `storage_analyze` | 综合分析 |
| `storage_chat` | 自然语言对话 |
| `storage_cleanup_duplicates` | 清理重复文件 |
| `storage_cleanup_large` | 清理大文件 |

## 使用示例

在 Claude Code 中：

```
你：分析一下 /data 目录的存储情况

Claude (调用 storage_stats)：
📊 /data 统计：
• 总文件：12,847
• 总大小：128.5 GB
• 最大类型：视频 (87.3 GB)
```

## 测试 MCP 服务器

```bash
# stdio 模式（用于 Claude Code）
python -m src.pristmax.agent.mcp_server --mode stdio

# HTTP 模式（用于 API 调用）
python -m src.pristmax.agent.mcp_server --mode http --port 5003
```

## API 端点

HTTP 模式下可用：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/mcp` | POST | MCP 协议端点 |
| `/tools` | GET | 列出所有工具 |

```bash
# 列出所有工具
curl http://localhost:5003/tools

# 调用工具
curl -X POST http://localhost:5003/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "storage_stats",
      "arguments": {"path": "/data"}
    }
  }'
```
