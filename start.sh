#!/bin/bash
#==============================================================================
# Pristmax 启动脚本（开发/测试用）
# 生产环境建议使用 systemd 服务
#==============================================================================

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 加载 .env 文件（如果存在）
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# 默认值
export PRISTMAX_DB="${PRISTMAX_DB:-$SCRIPT_DIR/data/tasks.db}"
export AUTH_DB="${AUTH_DB:-$SCRIPT_DIR/data/auth.db}"
export PORT="${PORT:-5001}"
export FLASK_ENV="${FLASK_ENV:-production}"

echo "======================================"
echo "  Pristmax API Server"
echo "======================================"
echo "数据库: $PRISTMAX_DB"
echo "端口:   $PORT"
echo "======================================"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "错误: 未找到虚拟环境，请先运行 deploy.sh 或创建虚拟环境"
    exit 1
fi

# 激活虚拟环境并启动
source venv/bin/activate
python -m src.pristmax.api.server --port $PORT --host 0.0.0.0
