"""
M5 API Module: Flask REST API Server with Authentication

功能:
- 任务管理 API
- 存储管理 API
- 策略管理 API
- 监控 API
- 用户认证 (JWT/API Key)
- 角色权限控制
- Web UI 静态文件
"""
import os
import sys
from pathlib import Path
from flask import Flask, request, jsonify, g
from flask_cors import CORS

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from unified.auth import require_auth, require_role, get_current_user, get_auth_manager, UserRole
from unified.monitor import get_monitor
from unified.scheduler import TaskScheduler, TaskPriority
from unified.storage import StorageManager
from unified.api.task_processor import register_all_handlers, TASK_HANDLERS

# 初始化任务调度器
task_scheduler = TaskScheduler(db_path="./tasks.db", max_workers=4)
register_all_handlers(task_scheduler)
task_scheduler.start()  # 启动调度器

# 初始化存储管理器
storage_manager = StorageManager()

# SSE 客户端订阅表
sse_subscriptions = {}  # task_id -> list of response objects

def notify_task_update(task_id: str, data: dict):
    """通知任务更新给所有订阅者"""
    if task_id in sse_subscriptions:
        for resp in sse_subscriptions[task_id]:
            try:
                resp.stream.send(f"data: {json.dumps(data)}\n\n")
            except:
                pass

# 创建 Flask 应用
app = Flask(__name__, static_folder='../web', static_url_path='')
CORS(app)

# 使用单例认证管理器（从环境变量读取配置）
auth_manager = get_auth_manager()


# ============== 辅助函数 ==============

def get_stats():
    """获取统计"""
    # 获取真实存储数据
    storages = storage_manager.list_storages()
    total_storage = sum(s.get('total_size', 0) for s in storages)
    used_storage = sum(s.get('used_size', 0) for s in storages)

    # 获取真实任务数据
    all_tasks = []
    for task in task_scheduler.db.conn.execute("SELECT status, COUNT(*) as count FROM tasks GROUP BY status"):
        all_tasks.append({'status': task[0], 'count': task[1]})

    task_counts = {
        'total': sum(t['count'] for t in all_tasks),
        'pending': next((t['count'] for t in all_tasks if t['status'] == 'pending'), 0),
        'running': next((t['count'] for t in all_tasks if t['status'] == 'running'), 0),
        'completed': next((t['count'] for t in all_tasks if t['status'] == 'completed'), 0),
        'failed': next((t['count'] for t in all_tasks if t['status'] == 'failed'), 0),
    }

    return {
        'storage': {
            'total_gb': round(total_storage / 1024**3, 1),
            'used_gb': round(used_storage / 1024**3, 1),
            'available_gb': round((total_storage - used_storage) / 1024**3, 1),
            'usage_percent': round((used_storage / max(total_storage, 1)) * 100, 1)
        },
        'tasks': task_counts,
        'dedup': {
            'total_chunks': 0,
            'unique_chunks': 0,
            'dedup_ratio': 0,
            'saved_gb': 0
        },
        'strategies': {
            'total': 4,
            'active': 2
        }
    }


# ============== 认证 API ==============

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json() or {}

    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify({'error': 'Missing required fields'}), 400

    user = auth_manager.register(username, email, password, UserRole.VIEWER)

    if not user:
        return jsonify({'error': 'User already exists'}), 409

    return jsonify({
        'message': 'User registered successfully',
        'user': {
            'user_id': user.user_id,
            'username': user.username,
            'email': user.email,
            'role': user.role.value,
            'api_key': user.api_key  # 首次注册显示 API Key
        }
    }), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json() or {}

    username = data.get('username')
    password = data.get('password')

    if not all([username, password]):
        return jsonify({'error': 'Missing required fields'}), 400

    token = auth_manager.login(username, password)

    if not token:
        return jsonify({'error': 'Invalid credentials'}), 401

    return jsonify({
        'token': token.token,
        'expires_at': token.expires_at,
        'user': {
            'user_id': token.user_id,
            'username': token.username,
            'role': token.role
        }
    })


@app.route('/api/auth/apikey/login', methods=['POST'])
def apikey_login():
    """API Key 登录"""
    data = request.get_json() or {}

    api_key = data.get('api_key')

    if not api_key:
        return jsonify({'error': 'Missing API key'}), 400

    token = auth_manager.login_api_key(api_key)

    if not token:
        return jsonify({'error': 'Invalid API key'}), 401

    return jsonify({
        'token': token.token,
        'expires_at': token.expires_at,
        'user': {
            'user_id': token.user_id,
            'username': token.username,
            'role': token.role
        }
    })


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def me():
    """获取当前用户信息"""
    user = get_current_user()
    return jsonify({
        'user_id': user.user_id,
        'username': user.username,
        'email': user.email,
        'role': user.role.value,
        'created_at': user.created_at,
        'last_login': user.last_login
    })


# ============== 统计 API ==============

@app.route('/api/stats', methods=['GET'])
def stats():
    """获取统计 (公开)"""
    return jsonify(get_stats())


# ============== 任务 API ==============

@app.route('/api/tasks', methods=['GET'])
@require_auth
def get_tasks():
    """获取任务列表"""
    user = get_current_user()
    tasks = task_scheduler.get_user_tasks(user.user_id)

    return jsonify({
        'tasks': [t.to_dict() for t in tasks]
    })


@app.route('/api/tasks/<task_id>', methods=['GET'])
@require_auth
def get_task(task_id):
    """获取单个任务"""
    task = task_scheduler.get_task_status(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    user = get_current_user()
    if task.user_id != user.user_id and user.role.value != 'admin':
        return jsonify({'error': 'Access denied'}), 403

    return jsonify(task.to_dict())


@app.route('/api/tasks', methods=['POST'])
@require_role('operator')
def create_task():
    """创建任务 (需操作员或管理员)"""
    data = request.get_json() or {}

    task_type = data.get('task_type')
    input_path = data.get('input_path')
    output_path = data.get('output_path', '')
    params = data.get('params', {})

    if not task_type or not input_path:
        return jsonify({'error': 'task_type and input_path are required'}), 400

    if task_type not in TASK_HANDLERS:
        return jsonify({'error': f'Unknown task type: {task_type}'}), 400

    user = get_current_user()
    task = task_scheduler.submit_task(
        task_type=task_type,
        user_id=user.user_id,
        input_path=input_path,
        output_path=output_path,
        params=params
    )

    return jsonify({
        'task_id': task.task_id,
        'status': task.status.value,
        'message': 'Task created successfully'
    }), 201


@app.route('/api/tasks/<task_id>/stream')
def task_stream(task_id):
    """
    SSE 任务进度流
    使用方式:
    const evtSource = new EventSource(`/api/tasks/${taskId}/stream`);
    evtSource.onmessage = (e) => {
        const data = JSON.parse(e.data);
        console.log('Progress:', data.progress, data.message);
    };
    """
    from flask import stream_with_context, Response

    def generate():
        # 发送初始连接消息
        yield f"data: {json.dumps({'type': 'connected', 'task_id': task_id})}\n\n"

        # 轮询任务状态变化
        last_status = None
        last_progress = -1

        while True:
            task = task_scheduler.get_task_status(task_id)
            if not task:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Task not found'})}\n\n"
                break

            # 只在状态或进度变化时发送更新
            if task.status.value != last_status or task.progress != last_progress:
                data = {
                    'type': 'update',
                    'task_id': task_id,
                    'status': task.status.value,
                    'progress': task.progress,
                    'message': task.progress_message or '',
                    'result': task.result if task.status.value == 'completed' else None,
                    'error': task.error if task.status.value == 'failed' else None
                }
                yield f"data: {json.dumps(data)}\n\n"
                last_status = task.status.value
                last_progress = task.progress

            # 任务结束则关闭流
            if task.status.value in ['completed', 'failed', 'cancelled']:
                break

            import time
            time.sleep(0.5)  # 500ms 轮询间隔

        yield f"data: {json.dumps({'type': 'done', 'status': last_status})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/tasks/<task_id>/cancel', methods=['POST'])
@require_auth
def cancel_task(task_id):
    """取消任务"""
    user = get_current_user()
    success = task_scheduler.cancel_task(task_id, user.user_id)

    if success:
        return jsonify({'status': 'cancelled'})
    else:
        return jsonify({'error': 'Cannot cancel task'}), 400


# ============== 存储 API ==============

@app.route('/api/storages', methods=['GET'])
@require_auth
def get_storages():
    """获取存储列表"""
    storages = storage_manager.list_storages()

    # 转换格式
    result = []
    for s in storages:
        result.append({
            'id': s.get('id', ''),
            'name': s.get('name', 'Unknown'),
            'type': s.get('type', 'unknown'),
            'path': s.get('path', ''),
            'total_gb': round(s.get('total_size', 0) / 1024**3, 1),
            'used_gb': round(s.get('used_size', 0) / 1024**3, 1),
            'available_gb': round(s.get('free_size', 0) / 1024**3, 1),
            'usage_percent': round((s.get('used_size', 0) / max(s.get('total_size', 1), 1)) * 100, 1),
            'status': s.get('status', 'unknown')
        })

    return jsonify({'storages': result})


@app.route('/api/storages', methods=['POST'])
@require_role('admin')
def add_storage():
    """添加存储 (仅管理员)"""
    data = request.get_json() or {}

    return jsonify({
        'name': data.get('name', 'New Storage'),
        'status': 'added',
        'message': 'Storage added successfully'
    }), 201


# ============== 策略 API ==============

@app.route('/api/strategies', methods=['GET'])
@require_auth
def get_strategies():
    """获取策略列表"""
    return jsonify({
        'strategies': [
            {
                'id': 'roi-blur-01',
                'name': 'ROI + 背景模糊',
                'type': 'roi_blur',
                'enabled': True,
                'crf': 28
            },
            {
                'id': 'asvc-01',
                'name': 'ASVC 背景差分',
                'type': 'asvc',
                'enabled': False,
                'crf': 28
            },
            {
                'id': 'blue-01',
                'name': 'BLUE 背景冻结',
                'type': 'blue',
                'enabled': False,
                'crf': 28
            },
            {
                'id': 'baseline-h265',
                'name': 'H.265 基线',
                'type': 'baseline',
                'enabled': True,
                'crf': 28
            }
        ]
    })


@app.route('/api/strategies/<strategy_id>', methods=['PUT'])
@require_role('admin')
def update_strategy(strategy_id):
    """更新策略 (仅管理员)"""
    data = request.get_json() or {}

    return jsonify({
        'status': 'updated',
        'strategy_id': strategy_id
    })


# ============== 告警 API ==============

@app.route('/api/alerts', methods=['GET'])
@require_auth
def get_alerts():
    """获取告警"""
    monitor = get_monitor()
    return jsonify({
        'alerts': [a.to_dict() for a in monitor.get_active_alerts()]
    })


@app.route('/api/alerts/<alert_id>/acknowledge', methods=['POST'])
@require_auth
def acknowledge_alert(alert_id):
    """确认告警"""
    monitor = get_monitor()
    monitor.acknowledge_alert(alert_id)
    return jsonify({'status': 'ok'})


# ============== 监控 API ==============

@app.route('/api/monitor/metrics', methods=['GET'])
@require_auth
def get_monitor_metrics():
    """获取当前系统指标"""
    monitor = get_monitor()
    metrics = monitor.get_current_metrics()
    return jsonify(metrics.to_dict() if metrics else {})


@app.route('/api/monitor/dashboard', methods=['GET'])
@require_auth
def get_monitor_dashboard():
    """获取监控面板数据"""
    monitor = get_monitor()
    return jsonify(monitor.get_dashboard_data())


@app.route('/api/monitor/prometheus', methods=['GET'])
def prometheus_metrics():
    """Prometheus 格式指标"""
    monitor = get_monitor()
    return monitor.export_prometheus(), 200, {'Content-Type': 'text/plain'}


# ============== Web UI ==============

@app.route('/')
def index():
    """主页"""
    return app.send_static_file('index.html')


@app.route('/dashboard')
def dashboard():
    """仪表盘"""
    return app.send_static_file('index.html')


@app.route('/web/<path:path>')
def static_files(path):
    """静态文件"""
    return app.send_from_directory('../web', path)


# ============== 健康检查 ==============

@app.route('/health')
def health():
    """健康检查"""
    return jsonify({'status': 'healthy'})


# ============== 主程序 ==============

def main():
    """主程序"""
    import argparse

    parser = argparse.ArgumentParser(description='Pristmax API Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host')
    parser.add_argument('--port', type=int, default=5001, help='Port')
    parser.add_argument('--debug', action='store_true', help='Debug mode')

    args = parser.parse_args()

    print(f"[API] Starting Pristmax API Server...")
    print(f"[API] Web UI: http://{args.host}:{args.port}/")
    print(f"[API] API: http://{args.host}:{args.port}/api/")
    print(f"[API] Auth: http://{args.host}:{args.port}/api/auth/login")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()

# 兼容旧接口
from pathlib import Path
