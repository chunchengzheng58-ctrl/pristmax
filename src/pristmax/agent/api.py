"""
Storage Agent API: Flask API for Storage Agent

提供存储管家的 HTTP API 接口
"""
import os
import sys
from pathlib import Path
from flask import Flask, jsonify, request

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.pristmax.agent.storage_agent import StorageAgent, FileInfo, DuplicateGroup

app = Flask(__name__)

# 全局 Agent 实例
_agent = None


def get_agent() -> StorageAgent:
    global _agent
    if _agent is None:
        db_path = os.environ.get('PRISTMAX_DB', ':memory:')
        _agent = StorageAgent(db_path=db_path)
    return _agent


@app.route('/api/agent/stats', methods=['GET'])
def get_storage_stats():
    """
    获取存储统计

    Query params:
        path: 扫描目录路径 (default: /)
    """
    scan_path = request.args.get('path', '/')

    if not os.path.exists(scan_path):
        return jsonify({'error': f'Path not found: {scan_path}'}), 400

    try:
        agent = get_agent()
        stats = agent.get_storage_stats(scan_path)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/agent/large-files', methods=['GET'])
def get_large_files():
    """
    获取大文件列表

    Query params:
        path: 扫描目录路径 (default: /)
        min_size_mb: 最小大小(MB) (default: 100)
        limit: 返回数量 (default: 20)
    """
    scan_path = request.args.get('path', '/')
    min_size_mb = int(request.args.get('min_size_mb', 100))
    limit = int(request.args.get('limit', 20))

    if not os.path.exists(scan_path):
        return jsonify({'error': f'Path not found: {scan_path}'}), 400

    try:
        agent = get_agent()
        files = agent.analyze_large_files(scan_path, min_size_mb=min_size_mb, limit=limit)
        return jsonify({
            'files': [asdict(f) for f in files],
            'count': len(files)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/agent/duplicates', methods=['GET'])
def get_duplicates():
    """
    查找重复文件

    Query params:
        path: 扫描目录路径 (default: /)
        min_size_kb: 最小大小(KB) (default: 1)
    """
    scan_path = request.args.get('path', '/')
    min_size_kb = int(request.args.get('min_size_kb', 1))

    if not os.path.exists(scan_path):
        return jsonify({'error': f'Path not found: {scan_path}'}), 400

    try:
        agent = get_agent()
        duplicates = agent.find_duplicates(scan_path, min_size_kb=min_size_kb)

        # 计算总节省空间
        total_wasted = sum(d.wasted_space for d in duplicates)

        return jsonify({
            'groups': [
                {
                    'hash': d.hash,
                    'size': d.size,
                    'size_display': d.size_display,
                    'count': d.count,
                    'files': d.files,
                    'wasted_space': d.wasted_space,
                    'wasted_display': FileInfo.format_size(d.wasted_space)
                }
                for d in duplicates
            ],
            'total_groups': len(duplicates),
            'total_wasted_space': total_wasted,
            'total_wasted_display': FileInfo.format_size(total_wasted)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/agent/analyze', methods=['POST'])
def analyze_storage():
    """
    综合分析存储

    Request body:
    {
        "path": "/path/to/scan",
        "options": {
            "scan_large_files": true,
            "find_duplicates": true,
            "get_stats": true
        }
    }
    """
    data = request.get_json() or {}
    scan_path = data.get('path', '/')
    options = data.get('options', {})

    if not os.path.exists(scan_path):
        return jsonify({'error': f'Path not found: {scan_path}'}), 400

    try:
        agent = get_agent()
        result = {}

        if options.get('get_stats', True):
            result['stats'] = agent.get_storage_stats(scan_path)

        if options.get('scan_large_files', True):
            result['large_files'] = [
                asdict(f) for f in agent.analyze_large_files(scan_path, min_size_mb=10, limit=10)
            ]

        if options.get('find_duplicates', False):
            duplicates = agent.find_duplicates(scan_path, min_size_kb=1024)  # 1MB+
            result['duplicates'] = {
                'groups': len(duplicates),
                'top_waste': [
                    {
                        'files': d.files,
                        'wasted': FileInfo.format_size(d.wasted_space)
                    }
                    for d in duplicates[:5]
                ]
            }

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/agent/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({'status': 'healthy', 'service': 'storage-agent'})


def main():
    """启动服务"""
    import argparse
    parser = argparse.ArgumentParser(description='Storage Agent API')
    parser.add_argument('--port', type=int, default=5002, help='Port')
    parser.add_argument('--host', default='0.0.0.0', help='Host')
    args = parser.parse_args()

    print(f"Starting Storage Agent API on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == '__main__':
    main()
