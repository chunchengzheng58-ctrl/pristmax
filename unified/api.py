# -*- coding: utf-8 -*-
"""
Unified Storage Reduction System - Web API Server

Combines:
- Semantic data reduction (监控视频、日志)
- Distributed dedup storage (CDC、去重、一致性哈希)
- Multi-storage abstraction (Local, NAS, USB, Cloud, RAID)
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import hashlib
import random

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

UI_ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)
CORS(app)

# =============================================================================
# Storage Layer Integration
# =============================================================================

try:
    from storage import storage_manager, StorageType
    STORAGE_AVAILABLE = True
except ImportError as e:
    print(f"[API] Storage module not available: {e}")
    STORAGE_AVAILABLE = False
    storage_manager = None

# =============================================================================
# In-Memory State
# =============================================================================

STATE = {
    # Cluster nodes
    'nodes': {
        'node-1': {'node_id': 'node-1', 'role': 'scan_node', 'host': '192.168.1.101', 'state': 'active', 'load': 32},
        'node-2': {'node_id': 'node-2', 'role': 'scan_node', 'host': '192.168.1.102', 'state': 'active', 'load': 45},
        'node-3': {'node_id': 'node-3', 'role': 'scan_node', 'host': '192.168.1.103', 'state': 'active', 'load': 28},
        'node-coord': {'node_id': 'node-coord', 'role': 'coordinator', 'host': '192.168.1.100', 'state': 'active', 'load': 15},
    },

    # Scan tasks
    'tasks': [
        {'task_id': 'task-001', 'path': '/data/backup', 'node_id': 'node-1', 'progress': 65, 'status': 'running'},
        {'task_id': 'task-002', 'path': '/data/logs', 'node_id': 'node-2', 'progress': 100, 'status': 'completed'},
        {'task_id': 'task-003', 'path': '/data/archive', 'node_id': None, 'progress': 0, 'status': 'pending'},
    ],

    # Cameras for semantic reduction
    'cameras': {
        'CAM-001': {'name': '大堂入口', 'type': 'indoor', 'storage': 0.65, 'savings': 0.42},
        'CAM-002': {'name': '停车场A区', 'type': 'parking', 'storage': 0.45, 'savings': 0.58},
        'CAM-003': {'name': '3层办公区', 'type': 'indoor', 'storage': 0.72, 'savings': 0.38},
    },

    # Policies for semantic reduction
    'policies': [
        {'id': 'policy-001', 'name': '办公楼3层策略', 'type': 'video', 'status': 'active', 'rules': ['人脸保留', '人员保留', '低价值10%']},
        {'id': 'policy-002', 'name': '停车场策略', 'type': 'video', 'status': 'active', 'rules': ['车辆保留', '人员保留', '低价值5%']},
        {'id': 'policy-003', 'name': '日志保留策略', 'type': 'log', 'status': 'draft', 'rules': ['ERROR保留', 'WARN保留', '采样10%']},
    ],

    # Stats
    'stats': {
        'total_saved_pb': 1.5,
        'dedup_ratio': 0.73,
        'semantic_ratio': 0.68,
        'annual_savings_cny': 1260000,
        'total_files': 45678,
        'total_chunks': 892345,
        'unique_chunks': 240932,
        'original_tb': 2400,
        'stored_tb': 648,
    }
}


# =============================================================================
# Static Files
# =============================================================================

@app.route('/')
def index():
    return send_from_directory(UI_ROOT, 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    if filename not in {'design.css', 'design.js', 'pristmax-editorial.css'}:
        return jsonify({'error': 'Not found'}), 404
    return send_from_directory(UI_ROOT, filename)


# =============================================================================
# Dashboard API
# =============================================================================

@app.route('/api/dashboard/stats')
def dashboard_stats():
    """Combined dashboard statistics"""
    stats = STATE['stats']
    return jsonify({
        'total_saved_pb': stats['total_saved_pb'],
        'dedup_ratio': stats['dedup_ratio'] * 100,
        'semantic_ratio': stats['semantic_ratio'] * 100,
        'combined_ratio': (stats['dedup_ratio'] + stats['semantic_ratio']) / 2 * 100,
        'node_count': len(STATE['nodes']),
        'annual_savings_cny': stats['annual_savings_cny'],
        'camera_count': len(STATE['cameras']),
        'task_count': len(STATE['tasks']),
    })


@app.route('/api/dashboard/activity')
def dashboard_activity():
    """Recent activity across both systems"""
    return jsonify([
        {'time': '10:30:45', 'source': 'CAM-001', 'type': 'semantic', 'action': '降采样', 'original': '100 MB', 'reduced': '10 MB', 'savings': '90%'},
        {'time': '10:28:12', 'source': 'backup-2024', 'type': 'dedup', 'action': '去重存储', 'original': '200 GB', 'reduced': '54 GB', 'savings': '73%'},
        {'time': '10:25:33', 'source': '/data/logs', 'type': 'dedup', 'action': 'CDC分块', 'original': '50 GB', 'reduced': '8 GB', 'savings': '84%'},
        {'time': '10:20:00', 'source': 'node-4', 'type': 'system', 'action': '节点注册', 'original': '-', 'reduced': '-', 'savings': '-'},
    ])


# =============================================================================
# Semantic Reduction API
# =============================================================================

@app.route('/api/semantic/cameras')
def list_cameras():
    return jsonify([
        {'id': k, **v} for k, v in STATE['cameras'].items()
    ])


@app.route('/api/semantic/policies')
def list_policies():
    return jsonify(STATE['policies'])


@app.route('/api/semantic/stats')
def semantic_stats():
    stats = STATE['stats']
    return jsonify({
        'cameras': len(STATE['cameras']),
        'active_policies': sum(1 for p in STATE['policies'] if p['status'] == 'active'),
        'reduction_ratio': stats['semantic_ratio'] * 100,
        'saved_tb': stats['original_tb'] * stats['semantic_ratio'],
    })


# =============================================================================
# Distributed Storage API
# =============================================================================

@app.route('/api/distributed/nodes')
def list_nodes():
    return jsonify(list(STATE['nodes'].values()))


@app.route('/api/distributed/nodes/<node_id>')
def get_node(node_id):
    if node_id not in STATE['nodes']:
        return jsonify({'error': 'Node not found'}), 404
    return jsonify(STATE['nodes'][node_id])


@app.route('/api/distributed/tasks')
def list_tasks():
    return jsonify(STATE['tasks'])


@app.route('/api/distributed/stats')
def distributed_stats():
    stats = STATE['stats']
    return jsonify({
        'nodes': len(STATE['nodes']),
        'healthy_nodes': sum(1 for n in STATE['nodes'].values() if n['state'] == 'active'),
        'dedup_ratio': stats['dedup_ratio'] * 100,
        'original_tb': stats['original_tb'],
        'stored_tb': stats['stored_tb'],
        'saved_tb': stats['original_tb'] - stats['stored_tb'],
        'total_files': stats['total_files'],
        'total_chunks': stats['total_chunks'],
        'unique_chunks': stats['unique_chunks'],
    })


# =============================================================================
# Audit API
# =============================================================================

@app.route('/api/audit/logs')
def audit_logs():
    """Combined audit logs from both systems"""
    return jsonify([
        {'time': '10:30:45', 'event': 'SEMANTIC_REDUCED', 'source': 'CAM-001', 'action': '降采样', 'original': '100 MB', 'reduced': '10 MB'},
        {'time': '10:28:12', 'event': 'DEDUP_STORED', 'source': 'backup-2024', 'action': '去重存储', 'original': '200 GB', 'reduced': '54 GB'},
        {'time': '10:25:33', 'event': 'CDC_CHUNKED', 'source': '/data/logs', 'action': '分块', 'original': '50 GB', 'reduced': '8 GB'},
        {'time': '10:20:00', 'event': 'NODE_REGISTERED', 'source': 'node-4', 'action': '注册', 'original': '-', 'reduced': '-'},
    ])


@app.route('/api/audit/verify')
def verify_audit():
    return jsonify({
        'valid': True,
        'total_entries': 6234,
        'first_entry': '2024-01-01 00:00:00',
        'last_entry': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


# =============================================================================
# Storage API (Multi-Storage Abstraction Layer)
# =============================================================================

@app.route('/api/storages')
def list_storages():
    """List all configured storages"""
    if not STORAGE_AVAILABLE:
        return jsonify({'error': 'Storage module not available', 'storages': []})

    storages = storage_manager.list_storages()
    return jsonify({'storages': storages})


@app.route('/api/storages', methods=['POST'])
def add_storage():
    """Add a new storage"""
    if not STORAGE_AVAILABLE:
        return jsonify({'error': 'Storage module not available'}), 500

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    storage_type = data.get('type', 'local_disk')
    config = data.get('config', {})

    # 合并 name 和 id
    if 'name' in data:
        config['name'] = data['name']
    if 'id' in data:
        config['id'] = data['id']

    storage_id = storage_manager.add_storage(storage_type, config)
    if storage_id:
        return jsonify({'status': 'ok', 'storage_id': storage_id})
    return jsonify({'error': 'Failed to add storage'}), 500


@app.route('/api/storages/<storage_id>', methods=['DELETE'])
def remove_storage(storage_id):
    """Remove a storage"""
    if not STORAGE_AVAILABLE:
        return jsonify({'error': 'Storage module not available'}), 500

    result = storage_manager.remove_storage(storage_id)
    if result:
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'Storage not found'}), 404


@app.route('/api/storages/<storage_id>/info')
def get_storage_info(storage_id):
    """Get storage details"""
    if not STORAGE_AVAILABLE:
        return jsonify({'error': 'Storage module not available'}), 500

    adapter = storage_manager.get_storage(storage_id)
    if not adapter:
        return jsonify({'error': 'Storage not found'}), 404

    info = adapter.get_info()
    return jsonify(info.to_dict())


@app.route('/api/storages/<storage_id>/scan', methods=['POST'])
def scan_storage(storage_id):
    """Scan a storage"""
    if not STORAGE_AVAILABLE:
        return jsonify({'error': 'Storage module not available'}), 500

    adapter = storage_manager.get_storage(storage_id)
    if not adapter:
        return jsonify({'error': 'Storage not found'}), 404

    data = request.get_json() or {}
    path = data.get('path', '/')
    recursive = data.get('recursive', True)

    files = []
    for file_info in storage_manager.scan_storage(storage_id, path, recursive):
        files.append(file_info.to_dict())

    return jsonify({
        'storage_id': storage_id,
        'path': path,
        'files_count': len(files),
        'files': files[:100],  # 限制返回数量
        'has_more': len(files) > 100
    })


@app.route('/api/storages/types')
def get_storage_types():
    """Get supported storage types"""
    types_info = [
        {'type': 'local_disk', 'name': '本地硬盘', 'description': 'SSD / HDD 磁盘', 'icon': '💾'},
        {'type': 'nas', 'name': 'NAS 存储', 'description': 'SMB / NFS 网络共享', 'icon': '📡'},
        {'type': 'usb', 'name': '外置硬盘', 'description': 'USB 存储设备', 'icon': '🔌'},
        {'type': 'cloud', 'name': '云存储', 'description': 'S3 兼容存储', 'icon': '☁️'},
        {'type': 'raid', 'name': 'RAID 阵列', 'description': '硬件 RAID 阵列', 'icon': '🗄️'},
    ]
    return jsonify({'types': types_info})


@app.route('/api/duplicates/find', methods=['POST'])
def find_duplicates():
    """Find duplicate files across storages"""
    if not STORAGE_AVAILABLE:
        return jsonify({'error': 'Storage module not available'}), 500

    data = request.get_json() or {}
    storage_ids = data.get('storage_ids', [])
    min_size = data.get('min_size', 1024)

    if not storage_ids:
        # 使用所有已配置的存储
        storages = storage_manager.list_storages()
        storage_ids = [s['id'] for s in storages]

    duplicates = storage_manager.find_duplicates(storage_ids, min_size)

    # 转换为列表格式
    duplicate_groups = []
    for file_hash, files in duplicates.items():
        group = {
            'hash': file_hash,
            'files': [f.to_dict() for f in files],
            'file_count': len(files),
            'total_size': sum(f.size for f in files),
            'wasted_size': sum(f.size for f in files) * (len(files) - 1)
        }
        duplicate_groups.append(group)

    return jsonify({
        'duplicate_groups': duplicate_groups,
        'total_groups': len(duplicate_groups),
        'total_duplicates': sum(g['file_count'] for g in duplicate_groups),
        'total_wasted_size': sum(g['wasted_size'] for g in duplicate_groups)
    })


# =============================================================================
# Health Check
# =============================================================================

@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0-unified'
    })


# =============================================================================
# Main
# =============================================================================

def _auto_discover_local_storage():
    """自动发现并添加本地磁盘"""
    if not STORAGE_AVAILABLE:
        return

    try:
        import platform
        import shutil

        if platform.system() == 'Windows':
            # Windows: 添加所有可用驱动器
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    try:
                        usage = shutil.disk_usage(drive)
                        storage_id = storage_manager.add_storage('local_disk', {
                            'id': f'local-{letter}',
                            'name': f'本地磁盘 ({letter}:)',
                            'mount_points': [drive],
                            'enabled': True
                        })
                        if storage_id:
                            print(f"  [Storage] Discovered: {drive} ({usage.total // (1024**3)} GB)")
                    except Exception as e:
                        pass
        else:
            # Unix/Linux: 添加根目录
            if os.path.exists('/'):
                storage_manager.add_storage('local_disk', {
                    'id': 'local-root',
                    'name': '根目录 (/)',
                    'mount_points': ['/'],
                    'enabled': True
                })
                print(f"  [Storage] Discovered: /")

    except Exception as e:
        print(f"  [Storage] Auto-discovery failed: {e}")


def main():
    print("="*70)
    print("Unified Storage Reduction System")
    print("="*70)
    print("\nCombined Features:")
    print("  - Semantic Reduction: 监控视频、日志智能降量")
    print("  - Distributed Storage: CDC分块、指纹去重、一致性哈希")
    print("  - Multi-Storage: Local / NAS / USB / Cloud / RAID")

    if STORAGE_AVAILABLE:
        print("\nStorage Adapters:")
        for st_type in StorageType:
            print(f"  - {st_type.value}")

        print("\nAuto-discovering local storage...")
        _auto_discover_local_storage()

    print("\nStarting server on http://localhost:5001")
    print("Open http://localhost:5001 in your browser")
    print("="*70)

    app.run(host='0.0.0.0', port=5001, debug=True)


if __name__ == '__main__':
    main()
