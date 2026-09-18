#!/bin/bash
#==============================================================================
# Pristmax 一键部署脚本
# 使用方法: chmod +x deploy.sh && ./deploy.sh
#==============================================================================

set -e

echo "======================================"
echo "  Pristmax B端 API 一键部署"
echo "======================================"

# 配置变量
APP_DIR="/opt/pristmax"
APP_USER="www-data"
APP_PORT="${PORT:-5001}"
PYTHON_VERSION="3.11"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# 检查是否为 root
if [[ $EUID -ne 0 ]]; then
   log_warn "建议使用 root 权限运行: sudo ./deploy.sh"
fi

# 检查操作系统
detect_os() {
    if [ -f /etc/debian_version ]; then
        OS="debian"
    elif [ -f /etc/redhat-release ]; then
        OS="rhel"
    elif [ -f /etc/alpine-release ]; then
        OS="alpine"
    else
        OS="unknown"
    fi
    log_info "检测到操作系统: $OS"
}

# 1. 安装系统依赖
install_dependencies() {
    log_step "安装系统依赖..."

    if [ "$OS" = "debian" ]; then
        apt-get update
        apt-get install -y \
            python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev \
            libgl1-mesa-glx libglib2.0-0 \
            libsm6 libxext6 libxrender-dev \
            sqlite3 curl
    elif [ "$OS" = "rhel" ]; then
        yum install -y \
            python${PYTHON_VERSION} \
            sqlite curl
        if ! command -v python${PYTHON_VERSION} &> /dev/null; then
            yum install -y python3.11
        fi
    else
        log_warn "未知操作系统，尝试安装通用依赖..."
        command -v python3 || apt-get install -y python3 python3-venv python3-dev
    fi

    log_info "系统依赖安装完成"
}

# 2. 创建用户
create_user() {
    log_step "创建应用用户..."

    if ! id -u $APP_USER &>/dev/null; then
        useradd -r -s /bin/false $APP_USER
        log_info "用户 $APP_USER 已创建"
    else
        log_info "用户 $APP_USER 已存在"
    fi
}

# 3. 创建目录
setup_directories() {
    log_step "创建应用目录..."

    mkdir -p $APP_DIR/data
    mkdir -p $APP_DIR/logs

    # 如果目录已存在且有旧文件，备份
    if [ -d "$APP_DIR/src" ] && [ "$(ls -A $APP_DIR/src 2>/dev/null)" ]; then
        BACKUP_DIR="$APP_DIR.backup.$(date +%Y%m%d%H%M%S)"
        log_warn "发现旧版本，备份到 $BACKUP_DIR"
        mv $APP_DIR $BACKUP_DIR
        mkdir -p $APP_DIR/data $APP_DIR/logs
    fi

    chown -R $APP_USER:$APP_USER $APP_DIR
    log_info "目录已创建: $APP_DIR"
}

# 4. 解压部署包
extract_package() {
    log_step "解压部署包..."

    # 查找部署包
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if [ -f "$SCRIPT_DIR/pristmax-api-release.tar" ]; then
        log_info "找到部署包: $SCRIPT_DIR/pristmax-api-release.tar"
        tar -xf "$SCRIPT_DIR/pristmax-api-release.tar" -C $APP_DIR/
    elif [ -f "/tmp/pristmax-api-release.tar" ]; then
        log_info "找到部署包: /tmp/pristmax-api-release.tar"
        tar -xf "/tmp/pristmax-api-release.tar" -C $APP_DIR/
    else
        log_warn "未找到部署包，尝试从 GitHub 下载..."
        download_from_github
    fi

    chown -R $APP_USER:$APP_USER $APP_DIR
    log_info "解压完成"
}

# 5. 从 GitHub 下载最新版本
download_from_github() {
    log_info "从 GitHub 下载最新版本..."

    # 使用 GitHub API 获取最新 release
    API_URL="https://api.github.com/repos/chunchengzheng58-ctrl/pristmax/releases/latest"

    if command -v curl &> /dev/null; then
        DOWNLOAD_URL=$(curl -s $API_URL | grep -o '"tarball_url": "[^"]*' | cut -d'"' -f4)
        if [ -n "$DOWNLOAD_URL" ]; then
            log_info "下载: $DOWNLOAD_URL"
            curl -L -o /tmp/pristmax-latest.tar.gz $DOWNLOAD_URL
            tar -xzf /tmp/pristmax-latest.tar.gz -C $APP_DIR/ --strip-components=1
            log_info "下载完成"
            return
        fi
    fi

    log_error "无法下载，请手动上传部署包"
    exit 1
}

# 6. 创建虚拟环境
setup_venv() {
    log_step "配置 Python 虚拟环境..."

    # 清理旧环境
    if [ -d "$APP_DIR/venv" ]; then
        rm -rf $APP_DIR/venv
    fi

    # 使用系统 Python 创建虚拟环境
    PYTHON_CMD="python${PYTHON_VERSION}"
    if ! command -v $PYTHON_CMD &> /dev/null; then
        PYTHON_CMD="python3"
    fi

    $PYTHON_CMD -m venv $APP_DIR/venv
    log_info "虚拟环境已创建"

    # 升级 pip
    $APP_DIR/venv/bin/pip install --upgrade pip --quiet
    log_info "pip 已升级"
}

# 7. 安装 Python 依赖
install_python_deps() {
    log_step "安装 Python 依赖..."

    # 安装依赖
    if [ -f "$APP_DIR/requirements-prod.txt" ]; then
        $APP_DIR/venv/bin/pip install -r $APP_DIR/requirements-prod.txt --quiet
        log_info "Python 依赖安装完成"
    else
        log_warn "未找到 requirements-prod.txt，安装基础依赖..."
        $APP_DIR/venv/bin/pip install flask flask-cors pyyaml bcrypt PyJWT psutil opencv-python numpy --quiet
    fi
}

# 8. 初始化数据库
init_database() {
    log_step "初始化数据库..."

    DB_FILE="$APP_DIR/data/tasks.db"

    if [ ! -f "$DB_FILE" ]; then
        $APP_DIR/venv/bin/python << PYEOF
import sqlite3
conn = sqlite3.connect('$DB_FILE')
conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY, task_type TEXT NOT NULL, user_id TEXT NOT NULL,
    input_path TEXT, output_path TEXT, params TEXT, status TEXT, priority INTEGER,
    result TEXT, error TEXT, progress REAL, progress_message TEXT,
    created_at TEXT, started_at TEXT, completed_at TEXT, retry_count INTEGER, max_retries INTEGER)''')
conn.execute('''CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
    crf INTEGER DEFAULT 28, preset TEXT DEFAULT 'medium', enabled INTEGER DEFAULT 1,
    config TEXT DEFAULT '{}', created_at TEXT, updated_at TEXT)''')
conn.execute('''CREATE TABLE IF NOT EXISTS alert_history (
    alert_id TEXT PRIMARY KEY, level TEXT NOT NULL, title TEXT NOT NULL, message TEXT,
    metric TEXT, value REAL, threshold REAL, timestamp TEXT,
    acknowledged INTEGER DEFAULT 0, acknowledged_by TEXT, acknowledged_at TEXT)''')
conn.execute('''CREATE TABLE IF NOT EXISTS notification_channels (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}', enabled INTEGER DEFAULT 1, created_at TEXT)''')
conn.execute('''CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT, alert_id TEXT,
    level TEXT, title TEXT, status TEXT, error TEXT, sent_at TEXT)''')
conn.commit()
conn.close()
print('Database initialized')
PYEOF
        log_info "数据库已初始化"
    else
        log_info "数据库已存在"
    fi

    chown $APP_USER:$APP_USER $DB_FILE
}

# 9. 配置环境变量
setup_env() {
    log_step "配置环境变量..."

    ENV_FILE="$APP_DIR/.env"

    if [ ! -f "$ENV_FILE" ]; then
        # 生成随机密钥
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

        cat > $ENV_FILE << EOF
# Pristmax 环境配置
PRISTMAX_DB=$APP_DIR/data/tasks.db
AUTH_DB=$APP_DIR/data/auth.db
PORT=$APP_PORT
FLASK_ENV=production
SECRET_KEY=$SECRET_KEY
PYTHONPATH=$APP_DIR
EOF
        log_info "环境变量已配置"
    else
        log_info "环境变量已存在"
    fi

    chown $APP_USER:$APP_USER $ENV_FILE
    chmod 600 $ENV_FILE
}

# 10. 配置 systemd 服务
setup_systemd() {
    log_step "配置系统服务..."

    cat > /etc/systemd/system/pristmax.service << EOF
[Unit]
Description=Pristmax B端 API Server
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python -m src.pristmax.api.server
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pristmax
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR/data

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_info "systemd 服务已配置"
}

# 11. 启动服务
start_service() {
    log_step "启动服务..."

    systemctl enable pristmax
    systemctl restart pristmax

    # 等待服务启动
    sleep 3

    # 检查状态
    if systemctl is-active --quiet pristmax; then
        log_info "服务启动成功!"
    else
        log_error "服务启动失败，查看日志:"
        journalctl -u pristmax -n 10 --no-pager
        exit 1
    fi
}

# 12. 验证部署
verify_deployment() {
    log_step "验证部署..."

    # 测试 API
    sleep 1
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${PORT}/api/stats 2>/dev/null || echo "000")

    if [ "$RESPONSE" = "200" ]; then
        log_info "API 服务验证成功!"
    else
        log_warn "API 服务响应异常 (HTTP $RESPONSE)，但服务已在运行"
    fi
}

# 主流程
main() {
    detect_os
    install_dependencies
    create_user
    setup_directories
    extract_package
    setup_venv
    install_python_deps
    init_database
    setup_env
    setup_systemd
    start_service
    verify_deployment

    echo ""
    echo "======================================"
    echo "  部署完成!"
    echo "======================================"
    echo ""
    echo "服务地址: http://localhost:${PORT}"
    echo "API 文档: http://localhost:${PORT}/api/stats"
    echo ""
    echo "管理命令:"
    echo "  查看状态: systemctl status pristmax"
    echo "  查看日志: journalctl -u pristmax -f"
    echo "  重启服务: systemctl restart pristmax"
    echo "  停止服务: systemctl stop pristmax"
    echo ""
    echo "配置文件: $APP_DIR/.env"
    echo "数据目录: $APP_DIR/data"
    echo "日志目录: $APP_DIR/logs"
    echo ""
}

main "$@"
