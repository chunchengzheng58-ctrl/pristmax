#!/bin/bash
#==============================================================================
# Pristmax 一键部署脚本
# 使用方法: chmod +x deploy.sh && ./deploy.sh
#==============================================================================

set -e

echo "======================================"
echo "  Pristmax 部署脚本"
echo "======================================"

# 配置变量
APP_DIR="/opt/pristmax"
APP_USER="www-data"
APP_PORT="5001"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查是否为 root
if [[ $EUID -ne 0 ]]; then
   log_warn "建议使用 root 权限运行，或在命令前加 sudo"
fi

# 1. 安装系统依赖
log_info "安装系统依赖..."
if command -v apt-get &> /dev/null; then
    apt-get update
    apt-get install -y \
        python3.11 python3.11-venv python3.11-dev \
        nginx certbot \
        libgl1-mesa-glx libglib2.0-0 \
        libsm6 libxext6 libxrender-dev \
        git
elif command -v yum &> /dev/null; then
    yum install -y \
        python311 python311-devel \
        nginx certbot \
        git
fi

# 2. 创建应用目录
log_info "创建应用目录..."
mkdir -p $APP_DIR
cd $APP_DIR

# 3. 创建用户（如不存在）
if ! id -u $APP_USER &>/dev/null; then
    log_info "创建用户 $APP_USER..."
    useradd -r -s /bin/false $APP_USER
fi

# 4. 上传项目文件（提示用户）
log_warn "请将项目文件上传到 $APP_DIR"
log_warn "可以使用: scp -r ./pristmax/* user@server:$APP_DIR/"
read -p "按 Enter 继续..."

# 5. 创建虚拟环境
log_info "创建 Python 虚拟环境..."
python3.11 -m venv venv
source venv/bin/activate

# 6. 安装 Python 依赖
log_info "安装 Python 依赖..."
pip install --upgrade pip
pip install -r requirements-prod.txt

# 7. 配置环境变量
if [ ! -f .env ]; then
    log_info "创建 .env 配置文件..."
    cp .env.example .env
    log_warn "请编辑 $APP_DIR/.env 设置 SECRET_KEY"
fi

# 8. 创建数据库目录
mkdir -p $APP_DIR/data
chown $APP_USER:$APP_USER $APP_DIR/data

# 9. 测试运行
log_info "测试运行..."
chown $APP_USER:$APP_USER $APP_DIR
sudo -u $APP_USER bash -c "source venv/bin/activate && PRISTMAX_DB=$APP_DIR/data/tasks.db python -c 'from src.pristmax.api.server import app; print(\"OK\")'"

# 10. 配置 systemd 服务
log_info "配置 systemd 服务..."
cat > /etc/systemd/system/pristmax.service << EOF
[Unit]
Description=Pristmax API Server
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PRISTMAX_DB=$APP_DIR/data/tasks.db"
Environment="AUTH_DB=$APP_DIR/data/auth.db"
Environment="PORT=$APP_PORT"
ExecStart=$APP_DIR/venv/bin/python -m src.pristmax.api.server
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 11. 启动服务
log_info "启动服务..."
systemctl daemon-reload
systemctl enable pristmax
systemctl start pristmax

# 12. 检查状态
sleep 2
if systemctl is-active --quiet pristmax; then
    log_info "服务启动成功!"
    echo ""
    echo "======================================"
    echo "  部署完成!"
    echo "======================================"
    echo "服务地址: http://localhost:$APP_PORT"
    echo "日志查看: journalctl -u pristmax -f"
    echo ""
    echo "后续步骤:"
    echo "1. 编辑 $APP_DIR/.env 设置 SECRET_KEY"
    echo "2. 配置 Nginx反向代理（可选）"
    echo "3. 配置 HTTPS（可选）"
else
    log_error "服务启动失败，请检查日志:"
    journalctl -u pristmax -n 20 --no-pager
fi
