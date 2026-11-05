# Storage Agent 中文使用文档

> 这是 [Storage Agent](README.md) 的完整中文文档，面向中文用户。
> 涵盖 CLI 参数、快速开始、常见问题（FAQ）以及 MCP 工具调用示例。
> 所有命令与参数均以当前代码 `src/pristmax/agent/cli.py` 和
> `src/pristmax/agent/mcp_server.py` 为准，如与英文 README 有出入，以本文件 + 源码为准。

## 目录

- [快速开始](#快速开始)
- [CLI 参数说明](#cli-参数说明)
- [MCP 工具使用示例](#mcp-工具使用示例)
- [常见问题 FAQ](#常见问题-faq)

---

## 快速开始

Storage Agent 是一个企业级存储优化工具，可以分析磁盘、查找重复文件、
清理大文件，并支持以 MCP 服务器形式接入 Claude Code / Cursor 等 MCP 客户端。

### 1. 安装

```bash
git clone https://github.com/chunchengzheng58-ctrl/pristmax.git
cd pristmax
pip install -e .
```

需要 Python 3.11+。可选依赖（按需安装）：

```bash
pip install flask flask-cors pyyaml watchdog apscheduler boto3
```

### 2. 第一次扫描

```bash
# 综合分析当前目录
python -m src.pristmax.agent.cli --analyze

# 分析指定目录并显示统计
python -m src.pristmax.agent.cli --stats --path /data

# 查找大于 100MB 的文件
python -m src.pristmax.agent.cli --large-files --min 100
```

### 3. 查找并清理重复文件

```bash
# 先预览（默认不会删除）
python -m src.pristmax.agent.cli --cleanup-duplicates --path /data

# 确认无误后再实际删除
python -m src.pristmax.agent.cli --cleanup-duplicates --path /data --execute
```

> `--cleanup-*` 默认处于预览（dry-run）模式，必须显式加 `--execute`
> 才会真正删除文件。这是为了防止误删。

---

## CLI 参数说明

启动方式：

```bash
python -m src.pristmax.agent.cli [选项...]
```

所有选项均来自 `cli.py` 中 `argparse` 的定义，按用途分组如下。

### 动作选项（选其一，缺省时默认执行 `--analyze`）

| 选项 | 作用 |
|------|------|
| `--analyze`, `-a` | 综合分析目录：总文件数、总大小、按类型分布 |
| `--large-files`, `-l` | 查找大于 `--min` 的大文件（默认 100MB） |
| `--duplicates`, `-d` | 查找重复文件（快速哈希 + 精确验证） |
| `--stats`, `-s` | 显示带进度条的统计信息 |
| `--export`, `-e` | 导出 HTML / JSON 报告 |
| `--suggest` | 显示智能优化建议 |
| `--cleanup-duplicates` | 清理重复文件（默认预览，需 `--execute` 才删除） |
| `--cleanup-large` | 清理大文件（默认预览，需 `--execute` 才删除） |
| `--chat` | 进入自然语言对话交互模式 |
| `--monitor` | 进入监控模式，周期性检测文件变化 |
| `--serve` | 启动 REST API 服务 |
| `--gui` | 启动 API 并自动打开浏览器 |
| `--desktop` | 整理桌面文件（默认预览，需 `--execute`） |
| `--undo` | 撤销上一次桌面整理 |

### 通用选项

| 选项 | 默认 | 说明 |
|------|------|------|
| `--path`, `-p` | 当前目录 | 要扫描的目录路径 |
| `--min` | `100` | 大小阈值；`--large-files`/`--cleanup-large` 时单位为 MB，`--duplicates`/`--cleanup-duplicates` 时单位为 KB |
| `--limit` | `20` | 返回结果数量上限 |
| `--db` | `:memory:` | SQLite 数据库路径。用内存库时缓存与审计不落盘；传入文件路径可持久化 |
| `--full-scan` | 关 | 禁用增量扫描，强制全量扫描 |
| `--format` | `html` | 报告格式，可选 `html` 或 `json` |
| `--output`, `-o` | 自动 | 报告输出路径（配合 `--export`） |
| `--interval` | `60` | 监控模式的检测间隔（秒） |
| `--port` | `5002` | API 服务端口 |
| `--execute` | 关 | 真正执行清理/整理操作。不加则全部为预览 |

### 桌面整理选项

| 选项 | 默认 | 说明 |
|------|------|------|
| `--desktop-mode` | `type` | 桌面整理模式：`type`（按文件类型）、`time`（按时间）、`project`（按项目关键词） |

整理结果统一放入桌面下的 `整理/` 文件夹；使用 `--undo` 可依据保存的
`.desktop_org_undo.json` 记录回滚。

### 常用示例

```bash
# 分析并导出 HTML 报告
python -m src.pristmax.agent.cli --export --path /data --format html -o report.html

# 查看某个目录的存储优化建议
python -m src.pristmax.agent.cli --suggest --path /data

# 启动 API 服务并打开浏览器
python -m src.pristmax.agent.cli --gui --port 5002

# 监控目录，每 30 秒检测一次
python -m src.pristmax.agent.cli --monitor --path /data --interval 30

# 全量重扫（忽略缓存）
python -m src.pristmax.agent.cli --stats --full-scan --path /data
```


---

## MCP 工具使用示例

Storage Agent 同时是一个 MCP 服务器（`mcp_server.py`），可接入
Claude Code、Cursor 等 MCP 客户端。服务器分 **只读**、**预览**、**审批**、
**安全配置**、**审计**、**缓存**、**监控**、**内容搜索**、**定时任务**、
**云存储**、**桌面同步**、**系统管理** 等类别。下面只列高频工具及真实入参
（与 `mcp_server.py` 中 `get_tools_list()` 的 `inputSchema` 一致）。

### 接入（Claude Code）

在 `claude_desktop_config.json` 中加入：

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

### 只读查询

`storage_stats` — 获取目录统计（`incremental` 默认 `true`）：

```json
{ "tool": "storage_stats", "arguments": { "path": "/data", "incremental": true } }
```

`storage_large_files` — 查找大文件（支持分页 `offset`）：

```json
{
  "tool": "storage_large_files",
  "arguments": { "path": "/data", "min_size_mb": 100, "limit": 20, "offset": 0 }
}
```

`storage_duplicates` — 查找重复文件：

```json
{ "tool": "storage_duplicates", "arguments": { "path": "/data", "min_size_kb": 1 } }
```

`storage_search_content` — 文件内容搜索（支持正则）：

```json
{
  "tool": "storage_search_content",
  "arguments": {
    "path": "/data",
    "keyword": "password",
    "file_types": [".py", ".js", ".json"],
    "max_results": 100
  }
}
```

### 清理预览与审批

`storage_cleanup_preview` — 预览清理（`type` 可为 `duplicates` / `large` /
`temp` / `old` / `empty`），**不会实际删除**：

```json
{ "tool": "storage_cleanup_preview", "arguments": { "path": "/data", "type": "duplicates" } }
```

真正删除需走审批流：

```json
{
  "tool": "storage_approval_action",
  "arguments": { "operation_id": "op-xxxx", "action": "approve", "approved_by": "mcp_user" }
}
```

> 服务器默认 `readonly_mode=True` 且 `require_approval=True`（见
> `mcp_server.py` 的 `main()`）。写操作必须先经 `storage_approval_action`
> 批准后才执行。

### 定时任务

`storage_schedule_add` — 用 Cron 表达式添加定时扫描：

```json
{
  "tool": "storage_schedule_add",
  "arguments": {
    "task_id": "nightly",
    "path": "/data",
    "schedule": "0 2 * * *",
    "task_type": "stats"
  }
}
```

### 云存储

`storage_cloud_config` — 配置 S3 / OSS（`provider` 为 `s3` 或 `oss`；
OSS 的 `region` 字段填 endpoint）：

```json
{
  "tool": "storage_cloud_config",
  "arguments": {
    "provider": "s3",
    "access_key": "AKIA...",
    "secret_key": "***",
    "bucket": "my-bucket",
    "region": "us-east-1"
  }
}
```

---

## 常见问题 FAQ

**Q：为什么有的命令看起来"没删东西"？**
A：`--cleanup-duplicates`、`--cleanup-large`、`--desktop` 以及 MCP 的
`storage_cleanup_preview` 默认都是**预览（dry-run）**模式，只列出将删除的
文件而不真正删除。要实际执行，CLI 加 `--execute`；MCP 走
`storage_approval_action` 审批。

**Q：`--min` 的单位到底是什么？**
A：`--min` 的单位取决于当前动作：`--large-files` / `--cleanup-large` 时是
MB，`--duplicates` / `--cleanup-duplicates` 时是 KB。这是有意设计，避免每次
换命令都调整数量级。

**Q：增量扫描是怎么加速的？**
A：`get_storage_stats` 默认 `incremental=True`，命中 SQLite 缓存（带 TTL）的
文件不再重扫，只处理新增/变更项。`--stats` 输出里会分别显示"缓存命中"和
"新增/变更"。加 `--full-scan` 可强制全量重扫。

**Q：MCP 服务器默认是只读的吗？**
A：是。`mcp_server.py` 的 `main()` 里 `--readonly` 和 `--require-approval`
默认均为 `True`。只读 + 需要审批的组合意味着删除类操作必须显式批准。需要
放宽时用 `--no-readonly` / `--no-approval`，生产环境不建议这样做。

**Q：如何让审计日志持久化？**
A：服务器默认用内存 SQLite（`:memory:`），进程结束即清空。启动时传 `--db
/path/to/storage.db`（CLI 与 MCP 都支持 `--db`）即可把扫描缓存、操作审批与
审计记录写入文件。

**Q：MCP 只连接上了读操作，写操作报"需要审批"怎么办？**
A：这是预期行为。先调用 `storage_cleanup_preview` 拿到 `operation_id`，再用
`storage_approval_action` 批准；批准后服务器会自动执行并回填结果。详见
`mcp_server.py` 中 `storage_approval_action` 的处理逻辑。

**Q：监控模式需要额外依赖吗？**
A：需要 `watchdog`（`pip install watchdog`）。若未安装，
`storage_monitor_start` 会返回一条提示"请安装 watchdog"的错误信息，
其它只读功能不受影响。

---

*本文档面向中文用户快速上手。如与源码行为不一致，请优先以
`src/pristmax/agent/cli.py` 与 `mcp_server.py` 为准，并欢迎提 issue 修正。*
