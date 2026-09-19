# Pristmax Desktop

**桌面端打包与部署指南**

---

## 快速开始

### Windows

**方式一：直接运行**
```bash
# 双击 start.bat 或在命令行运行
start.bat
```

**方式二：从源码运行**
```bash
pip install flask flask-cors pyyaml
python main.py --host 0.0.0.0 --port 5000
```

**方式三：打包成 .exe**
```bash
pip install pyinstaller
python scripts/build_desktop.py
# 输出: dist/Pristmax.exe
```

### macOS / Linux

```bash
chmod +x start.sh
./start.sh
```

---

## Docker 部署

### 构建镜像

```bash
docker build -f Dockerfile.desktop -t pristmax:desktop .
```

### 运行容器

```bash
docker run -d \
  --name pristmax \
  -p 5000:5000 \
  -v /path/to/data:/data \
  pristmax:desktop
```

---

## 打包说明

### 打包脚本

```bash
# 查看帮助
python scripts/build_desktop.py --help

# 构建 Windows .exe
python scripts/build_desktop.py --platform win

# 构建 Unix 可执行文件
python scripts/build_desktop.py --platform unix

# 清理构建产物
python scripts/build_desktop.py --clean
```

### PyInstaller 配置 (main.spec)

```python
a = Analysis(
    ['main.py'],
    datas=[
        ('src/pristmax/web', 'src/pristmax/web'),
        ('src/pristmax/site', 'src/pristmax/site'),
    ],
    hiddenimports=[
        'flask', 'flask_cors', 'werkzeug',
        'src.pristmax.auth',
        'src.pristmax.storage',
        'src.pristmax.api.server',
    ],
)
exe = EXE(pyz, a.scripts, ..., console=False)
```

---

## 目录结构

```
pristmax/
├── main.py              # 应用入口
├── main.spec            # PyInstaller 配置
├── start.bat            # Windows 启动脚本
├── start.sh             # Unix 启动脚本
├── scripts/
│   └── build_desktop.py # 打包脚本
├── Dockerfile.desktop    # Docker 部署
├── src/pristmax/
│   ├── api/            # REST API
│   ├── web/            # 管理控制台
│   ├── agent/          # Storage Agent CLI
│   └── site/           # 营销网站
└── dist/               # 打包输出目录
```

---

## 系统要求

| 项目 | 最低要求 |
|------|----------|
| 操作系统 | Windows 10+, macOS 10.14+, Ubuntu 18.04+ |
| Python | 3.10+ |
| 内存 | 512 MB |
| 磁盘 | 100 MB 可用空间 |

---

## 网络配置

| 端口 | 说明 |
|------|------|
| 5001 | Web 控制台 + API |
| 5002 | Storage Agent API |
| 5003 | MCP Server (可选) |

生产环境建议配合 nginx 反向代理。
