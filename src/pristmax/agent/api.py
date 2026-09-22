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


@app.route('/')
def index():
    """Web UI 入口"""
    return '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Storage Agent - 智能存储管家</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, sans-serif; background: #f4f9fc; min-height: 100vh; }
        .header { background: #173d58; color: white; padding: 20px 40px; }
        .header h1 { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
        .header p { font-size: 14px; opacity: 0.8; }
        .container { max-width: 1200px; margin: 40px auto; padding: 0 20px; }
        .card { background: white; border-radius: 12px; padding: 30px; margin-bottom: 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
        .card h2 { font-size: 18px; color: #173d58; margin-bottom: 20px; border-bottom: 1px solid #e8f0f6; padding-bottom: 12px; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; font-size: 14px; color: #587185; margin-bottom: 8px; }
        .form-group input { width: 100%; max-width: 500px; padding: 12px 16px; border: 1px solid #cbdce8; border-radius: 8px; font-size: 14px; }
        .form-group input:focus { outline: none; border-color: #285f83; box-shadow: 0 0 0 3px rgba(40,95,131,0.1); }
        .btn { padding: 12px 24px; background: #173d58; color: white; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; }
        .btn:hover { background: #0c2854; }
        .btn-secondary { background: #e8f0f6; color: #173d58; }
        .btn-secondary:hover { background: #d0e4f0; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 20px; }
        .stat-item { background: #f8fafc; padding: 20px; border-radius: 8px; text-align: center; }
        .stat-value { font-size: 32px; font-weight: 700; color: #173d58; }
        .stat-label { font-size: 12px; color: #587185; margin-top: 8px; text-transform: uppercase; letter-spacing: 1px; }
        .results { margin-top: 20px; }
        .result-item { padding: 16px; background: #f8fafc; border-radius: 8px; margin-bottom: 12px; }
        .result-item h4 { color: #173d58; font-size: 14px; margin-bottom: 8px; }
        .result-item p { font-size: 13px; color: #587185; }
        .result-item .size { color: #285f83; font-weight: 600; }
        .loading { text-align: center; padding: 40px; color: #587185; }
        .error { background: #fef2f2; color: #dc2626; padding: 16px; border-radius: 8px; margin-top: 16px; }
        .api-info { background: #173d58; color: white; padding: 20px; border-radius: 8px; margin-top: 20px; }
        .api-info code { background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-size: 13px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🗄️ Storage Agent</h1>
        <p>智能存储管家 - 分析、去重、优化</p>
    </div>
    <div class="container">
        <div class="card">
            <h2>📊 快速分析</h2>
            <div class="form-group">
                <label>扫描目录路径</label>
                <input type="text" id="scanPath" value="C:\\" placeholder="输入要扫描的目录路径">
            </div>
            <button class="btn" onclick="analyze()">开始分析</button>
            <button class="btn btn-secondary" onclick="findDuplicates()">查找重复文件</button>
        </div>

        <div id="results" class="card" style="display:none;">
            <h2>分析结果</h2>
            <div id="statsGrid" class="stats-grid"></div>
            <div id="resultsList" class="results"></div>
        </div>

        <div id="loading" class="card loading" style="display:none;">
            <p>分析中，请稍候...</p>
        </div>

        <div id="error" class="error" style="display:none;"></div>

        <div class="card">
            <h2>🔌 API 接口</h2>
            <p style="color:#587185;font-size:14px;margin-bottom:16px;">可直接调用 REST API 集成到其他系统：</p>
            <div class="api-info">
                <p><code>GET /api/agent/stats?path=C:\\</code> - 获取存储统计</p>
                <p style="margin-top:8px;"><code>GET /api/agent/large-files?path=C:\\&amp;min_size_mb=100</code> - 大文件列表</p>
                <p style="margin-top:8px;"><code>GET /api/agent/duplicates?path=C:\\</code> - 重复文件</p>
                <p style="margin-top:8px;"><code>GET /api/agent/health</code> - 健康检查</p>
            </div>
        </div>
    </div>

    <script>
    const API = '';
    const resultsDiv = document.getElementById('results');
    const loadingDiv = document.getElementById('loading');
    const errorDiv = document.getElementById('error');
    const statsGrid = document.getElementById('statsGrid');
    const resultsList = document.getElementById('resultsList');

    function showLoading() {
        resultsDiv.style.display = 'none';
        loadingDiv.style.display = 'block';
        errorDiv.style.display = 'none';
    }

    function showError(msg) {
        loadingDiv.style.display = 'none';
        errorDiv.style.display = 'block';
        errorDiv.textContent = msg;
    }

    function showResults() {
        loadingDiv.style.display = 'none';
        resultsDiv.style.display = 'block';
        errorDiv.style.display = 'none';
    }

    function formatSize(bytes) {
        if (bytes >= 1073741824) return (bytes/1073741824).toFixed(1) + ' GB';
        if (bytes >= 1048576) return (bytes/1048576).toFixed(1) + ' MB';
        if (bytes >= 1024) return (bytes/1024).toFixed(1) + ' KB';
        return bytes + ' B';
    }

    async function analyze() {
        const path = document.getElementById('scanPath').value;
        if (!path) { showError('请输入路径'); return; }

        showLoading();
        try {
            const resp = await fetch(API + '/api/agent/stats?path=' + encodeURIComponent(path));
            if (!resp.ok) throw new Error('扫描失败: ' + resp.statusText);
            const data = await resp.json();

            // 显示统计
            statsGrid.innerHTML = `
                <div class="stat-item"><div class="stat-value">${data.total_files || 0}</div><div class="stat-label">文件总数</div></div>
                <div class="stat-item"><div class="stat-value">${formatSize(data.total_size || 0)}</div><div class="stat-label">总大小</div></div>
                <div class="stat-item"><div class="stat-value">${Object.keys(data.by_category || {}).length}</div><div class="stat-label">类型数</div></div>
            `;

            // 显示分类
            const cats = data.by_category || {};
            let html = '<h3 style="margin:20px 0 12px;color:#173d58;">按类型分布</h3>';
            for (const [cat, info] of Object.entries(cats)) {
                html += `<div class="result-item">
                    <h4>${cat}</h4>
                    <p>${info.count} 个文件，<span class="size">${info.size_display}</span></p>
                </div>`;
            }
            resultsList.innerHTML = html;
            showResults();
        } catch (e) {
            showError(e.message);
        }
    }

    async function findDuplicates() {
        const path = document.getElementById('scanPath').value;
        if (!path) { showError('请输入路径'); return; }

        showLoading();
        try {
            const resp = await fetch(API + '/api/agent/duplicates?path=' + encodeURIComponent(path) + '&min_size_kb=1');
            if (!resp.ok) throw new Error('查找失败: ' + resp.statusText);
            const data = await resp.json();

            statsGrid.innerHTML = `
                <div class="stat-item"><div class="stat-value">${data.total_groups || 0}</div><div class="stat-label">重复组数</div></div>
                <div class="stat-item"><div class="stat-value">${formatSize(data.total_wasted_space || 0)}</div><div class="stat-label">可节省空间</div></div>
            `;

            let html = '<h3 style="margin:20px 0 12px;color:#173d58;">重复文件组</h3>';
            const groups = data.groups || [];
            for (const g of groups.slice(0, 10)) {
                html += `<div class="result-item">
                    <h4>${g.count} 个相同文件，每文件 ${g.size_display}</h4>
                    <p>可节省: <span class="size">${g.wasted_display}</span></p>
                </div>`;
            }
            resultsList.innerHTML = html;
            showResults();
        } catch (e) {
            showError(e.message);
        }
    }
    </script>
</body>
</html>
    '''


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
