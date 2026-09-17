# Pristmax Storage - Docker 部署指南

## 快速开始

### 1. 构建镜像

```bash
cd unified
docker build -t pristmax-storage:latest .
```

### 2. 使用 Docker Compose 启动

```bash
docker-compose up -d
```

### 3. 访问服务

- Web UI: http://localhost:5001
- API: http://localhost:5001/api/stats

---

## Docker Compose 配置说明

```yaml
services:
  pristmax:
    build: .              # 构建镜像
    container_name: pristmax-storage
    ports:
      - "5001:5001"      # API 端口
      - "9090:9090"      # 监控端口
    volumes:
      - ./data:/app/data       # 数据目录
      - ./storage:/app/storage # 存储卷
      - ./logs:/app/logs       # 日志
      - ./config:/app/config   # 配置
    environment:
      - PRISTMAX_HOST=0.0.0.0
      - PRISTMAX_PORT=5001
      - PRISTMAX_DEBUG=false
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PRISTMAX_HOST` | 0.0.0.0 | 监听地址 |
| `PRISTMAX_PORT` | 5001 | API 端口 |
| `PRISTMAX_DEBUG` | false | 调试模式 |
| `PRISTMAX_STORAGE_PATH` | /app/storage | 存储路径 |

---

## 数据持久化

生产环境建议挂载以下目录:

- `./storage` → `/app/storage` (用户数据)
- `./data` → `/app/data` (SQLite 数据库)
- `./logs` → `/app/logs` (日志)
- `./config` → `/app/config` (配置)

---

## 生产环境部署

### 1. 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. 使用 Systemd 服务

```ini
[Unit]
Description=Pristmax Storage
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/pristmax
ExecStart=/usr/bin/docker-compose up
Restart=always

[Install]
WantedBy=multi-user.target
```

### 3. 使用 K8s (Kubernetes)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pristmax-storage
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pristmax-storage
  template:
    metadata:
      labels:
        app: pristmax-storage
    spec:
      containers:
      - name: pristmax
        image: pristmax-storage:latest
        ports:
        - containerPort: 5001
        volumeMounts:
        - name: storage
          mountPath: /app/storage
      volumes:
      - name: storage
        persistentVolumeClaim:
          claimName: pristmax-storage-pvc
```

---

## 健康检查

```bash
# 检查容器健康状态
docker inspect pristmax-storage --format='{{.State.Health.Status}}'

# 手动健康检查
curl -f http://localhost:5001/api/stats
```

---

## 日志查看

```bash
# 容器日志
docker logs -f pristmax-storage

# 应用日志
docker exec pristmax-storage tail -f /app/logs/app.log
```

---

## 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建
docker-compose build

# 重启服务
docker-compose up -d
```

---

## 资源限制

建议生产环境配置:

- CPU: 4 核+
- 内存: 8GB+
- 磁盘: 根据存储需求
