# Pristmax 普里斯特麦克斯

**Less storage. More clarity.**

更少的存储，更多的清晰。

[![CI](https://github.com/chunchengzheng58-ctrl/pristmax/actions/workflows/ci.yml/badge.svg)](https://github.com/chunchengzheng58-ctrl/pristmax/actions)
[![Release](https://img.shields.io/github/v/release/chunchengzheng58-ctrl/pristmax?include_prereleases)](https://github.com/chunchengzheng58-ctrl/pristmax/releases)
[![License](https://img.shields.io/github/license/chunchengzheng58-ctrl/pristmax)](LICENSE)

企业级数据存储优化系统 — 本地运行，验证完整性，减少占用空间。

[官网](https://jiangchenghehe.top) · [文档](src/pristmax/site/docs.html) · [更新日志](CHANGELOG.md)

---

## 特性

| 特性 | 说明 |
|------|------|
| 📊 **存储分析** | 按类型、大小、位置扫描和分类文件 |
| 🔄 **去重** | 查找并删除重复文件节省空间 |
| 📦 **大文件** | 识别占用空间大的文件 |
| 🤖 **AI 集成** | 通过 MCP 协议与 Claude Code、Cursor 等集成 |
| 🌐 **REST API** | 与其他系统集成 |
| 📱 **Web 控制台** | 友好的管理界面 |

---

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/chunchengzheng58-ctrl/pristmax.git
cd pristmax

# 安装依赖
pip install flask flask-cors pyyaml

# 运行
python main.py --host 0.0.0.0 --port 5000
```

打开 http://localhost:5000

### Storage Agent 命令行

```bash
# 分析目录
python -m src.pristmax.agent.cli --path /data --analyze

# 查找大文件
python -m src.pristmax.agent.cli --large-files --min 100

# 查找重复文件
python -m src.pristmax.agent.cli --duplicates

# 获取统计
python -m src.pristmax.agent.cli --stats

# 自然语言对话
python -m src.pristmax.agent.cli --chat

# 启动 API 服务
python -m src.pristmax.agent.cli --serve --port 5002
```

---

## AI 集成 (MCP)

Storage Agent 支持 [MCP 协议](https://modelcontextprotocol.io/)，可与 AI 助手集成。

### Claude Code 配置

编辑 `settings.json`：

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

### 可用工具

| 工具 | 说明 |
|------|------|
| `storage_stats` | 获取目录统计 |
| `storage_large_files` | 查找大文件 |
| `storage_duplicates` | 查找重复文件 |
| `storage_suggestions` | 获取优化建议 |
| `storage_analyze` | 综合分析 |
| `storage_chat` | 自然语言问答 |
| `storage_cleanup_duplicates` | 清理重复文件（预览） |
| `storage_cleanup_large` | 清理大文件（预览） |

---

## 项目结构

```
pristmax/
├── src/pristmax/        ← 开源核心 (Apache 2.0)
│   ├── api/            REST API 服务
│   ├── web/            管理控制台
│   ├── scheduler/      任务调度
│   ├── storage/        存储抽象层
│   ├── auth/           认证与权限
│   ├── monitor/        系统监控
│   └── agent/          Storage Agent CLI & MCP
├── site/               官网前端
├── mcp/                MCP 协议文档
├── commercial/          ← 专有软件 (单独授权)
│   ├── encoder/        H.265 视频编码
│   └── surveillance/   视频分析
└── main.py             应用入口
```

---

## 支持的存储后端

| 类型 | 状态 |
|------|------|
| 本地磁盘 | ✅ |
| NAS (SMB/NFS) | ✅ |
| U盘 | ✅ |
| 云存储 (S3/OSS/COS) | ✅ |
| RAID | ✅ |

---

## 开源理念

**商业部分不开源。**

| 类别 | 状态 |
|------|------|
| 开源核心 (Apache 2.0) | ✅ GitHub 公开 |
| 专有组件 | 🔒 不公开，需要单独授权 |

---

## 贡献

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

请遵守我们的 [行为准则](CODE_OF_CONDUCT.md) 和 [安全政策](SECURITY.md)。

---

## 许可证

开源组件：Apache 2.0

专有组件（H.265 编码器、视频分析）：[联系授权](mailto:[pending])

---

## 联系方式

- 官网：https://jiangchenghehe.top
- GitHub：https://github.com/chunchengzheng58-ctrl/pristmax
- 问题反馈：[GitHub Issues](https://github.com/chunchengzheng58-ctrl/pristmax/issues)
