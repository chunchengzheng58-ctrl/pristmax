# Pristmax B端 API 部署指南

## 快速部署（推荐）

```bash
# 1. 上传项目到服务器
scp -r . user@your-server:/opt/pristmax/

# 2. SSH 登录服务器
ssh user@your-server

# 3. 一键部署
chmod +x /opt/pristmax/deploy.sh
sudo /opt/pristmax/deploy.sh
```

## 手动部署

### 1. 安装依赖

```bash
# Ubuntu/Debian
apt update && apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    nginx certbot \
    libgl1-mesa-glx libglib2.0-0

# CentOS/RHEL
yum install -y \
    python311 python311-devel \
    nginx certbot
```

### 2. 创建目录和用户

```bash
mkdir -p /opt/pristmax/data
useradd -r -s /bin/false pristmax || true
chown -R pristmax:pristmax /opt/pristmax
```

### 3. 配置环境变量

```bash
cd /opt/pristmax
cp .env.example .env
nano .env  # 编辑 SECRET_KEY
```

### 4. 安装 Python 依赖

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements-prod.txt
```

### 5. 测试运行

```bash
PRISTMAX_DB=/opt/pristmax/data/tasks.db \
    python -c "from src.pristmax.api.server import app; print('OK')"
```

### 6. 配置 systemd 服务

```bash
cp pristmax.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable pristmax
systemctl start pristmax
```

### 7. Nginx 反向代理（可选）

```bash
cp nginx.conf.example /etc/nginx/sites-available/pristmax
nano /etc/nginx/sites-available/pristmax  # 修改域名
ln -sf /etc/nginx/sites-available/pristmax /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 8. 配置 HTTPS（可选）

```bash
certbot --nginx -d your-domain.com
```

## 目录结构

```
/opt/pristmax/
├── src/                 # 源代码
├── commercial/          # 编码器
├── data/               # 数据目录（tasks.db, auth.db）
├── venv/               # Python 虚拟环境
├── .env                # 环境变量
├── requirements-prod.txt
├── start.sh            # 启动脚本
├── deploy.sh           # 部署脚本
└── pristmax.service    # systemd 服务
```

## 服务管理

```bash
# 启动
sudo systemctl start pristmax

# 停止
sudo systemctl stop pristmax

# 重启
sudo systemctl restart pristmax

# 查看状态
sudo systemctl status pristmax

# 查看日志
sudo journalctl -u pristmax -f
```

## API 地址

- 本地测试: `http://localhost:5001`
- Nginx 代理: `http://your-domain.com`
- HTTPS: `https://your-domain.com`

## 常用 API

```bash
# 健康检查
curl http://localhost:5001/health

# 获取统计
curl http://localhost:5001/api/stats

# 登录获取 Token
curl -X POST http://localhost:5001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password"}'

# 创建 ROI 任务
curl -X POST http://localhost:5001/api/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"task_type":"roi","input_path":"/path/to/video.mp4","params":{"crf":28}}'
```

## 故障排除

### 服务启动失败

```bash
# 查看详细日志
sudo journalctl -u pristmax -n 50 --no-pager

# 手动运行测试
cd /opt/pristmax
source venv/bin/activate
PRISTMAX_DB=/opt/pristmax/data/tasks.db python -m src.pristmax.api.server
```

### 数据库问题

```bash
# 检查数据库文件
ls -la /opt/pristmax/data/

# 重建数据库（如需要）
# rm /opt/pristmax/data/tasks.db
# 重启服务会自动创建
```

### 权限问题

```bash
# 确保目录权限正确
chown -R pristmax:pristmax /opt/pristmax
chmod 755 /opt/pristmax
chmod 700 /opt/pristmax/data
```
