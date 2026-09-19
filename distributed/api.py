# -*- coding: utf-8 -*-
"""
Distributed Storage System - Web API Server

REST API for:
- Cluster overview
- Node management
- Task scheduling
- Sharding configuration
- Storage analytics
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

app = Flask(__name__, static_folder='.')
CORS(app)

# In-memory cluster state (would be etcd/ScyllaDB in production)
CLUSTER_STATE = {
    'nodes': {
        'node-1': {
            'node_id': 'node-1',
            'role': 'scan_node',
            'host': '192.168.1.101',
            'port': 9042,
            'state': 'active',
            'capacity': {'files_per_sec': 1000},
            'current_load': 32,
            'last_heartbeat': datetime.now().isoformat() + 'Z',
        },
        'node-2': {
            'node_id': 'node-2',
            'role': 'scan_node',
            'host': '192.168.1.102',
            'port': 9042,
            'state': 'active',
            'capacity': {'files_per_sec': 1000},
            'current_load': 45,
            'last_heartbeat': datetime.now().isoformat() + 'Z',
        },
        'node-3': {
            'node_id': 'node-3',
            'role': 'scan_node',
            'host': '192.168.1.103',
            'port': 9042,
            'state': 'active',
            'capacity': {'files_per_sec': 1000},
            'current_load': 28,
            'last_heartbeat': datetime.now().isoformat() + 'Z',
        },
        'node-coord': {
            'node_id': 'node-coord',
            'role': 'coordinator',
            'host': '192.168.1.100',
            'port': 2379,
            'state': 'active',
            'capacity': {'tasks': 100},
            'current_load': 15,
            'last_heartbeat': datetime.now().isoformat() + 'Z',
        },
    },
    'tasks': [
        {
            'task_id': 'task-001',
            'path': '/data/backup',
            'node_id': 'node-1',
            'progress': 65,
            'status': 'running',
            'created_at': (datetime.now() - timedelta(hours=2)).isoformat() + 'Z',
        },
        {
            'task_id': 'task-002',
            'path': '/data/logs',
            'node_id': 'node-2',
            'progress': 100,
            'status': 'completed',
            'created_at': (datetime.now() - timedelta(hours=5)).isoformat() + 'Z',
        },
        {
            'task_id': 'task-003',
            'path': '/data/archive',
            'node_id': None,
            'progress': 0,
            'status': 'pending',
            'created_at': (datetime.now() - timedelta(hours=1)).isoformat() + 'Z',
        },
    ],
    'sharding': {
        'virtual_nodes_per_physical': 150,
        'total_shards': 256,
        'replication_factor': 3,
        'ring': [
            {'start': 0x00, 'end': 0x3F, 'primary': 'node-1', 'replicas': ['node-2', 'node-3']},
            {'start': 0x40, 'end': 0x7F, 'primary': 'node-2', 'replicas': ['node-3', 'node-1']},
            {'start': 0x80, 'end': 0xBF, 'primary': 'node-3', 'replicas': ['node-1', 'node-2']},
            {'start': 0xC0, 'end': 0xFF, 'primary': 'node-1', 'replicas': ['node-3', 'node-2']},
        ]
    },
    'stats': {
        'total_files': 45678,
        'total_chunks': 892345,
        'unique_chunks': 240932,
        'duplicate_chunks': 651413,
        'dedup_ratio': 0.73,
        'original_bytes': 2.4 * 1024**4,
        'stored_bytes': 0.648 * 1024**4,
        'storage_cost_per_tb': 5000,
    }
}


# =============================================================================
# Static Files
# =============================================================================

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('.', 'distributed.html')


@app.route('/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('.', filename)


# =============================================================================
# Cluster API
# =============================================================================

@app.route('/api/cluster/stats')
def cluster_stats():
    """Get cluster statistics"""
    nodes = CLUSTER_STATE['nodes']
    healthy = sum(1 for n in nodes.values() if n['state'] == 'active')

    stats = CLUSTER_STATE['stats']
    savings = stats['original_bytes'] - stats['stored_bytes']
    savings_cny = savings / 1024**4 * stats['storage_cost_per_tb'] * 12  # Annual

    return jsonify({
        'total_nodes': len(nodes),
        'healthy_nodes': healthy,
        'replication_factor': CLUSTER_STATE['sharding']['replication_factor'],
        'virtual_nodes_per_physical': CLUSTER_STATE['sharding']['virtual_nodes_per_physical'],
        'total_files': stats['total_files'],
        'dedup_ratio': round(stats['dedup_ratio'] * 100, 1),
        'original_tb': round(stats['original_bytes'] / 1024**4, 2),
        'stored_tb': round(stats['stored_bytes'] / 1024**4, 2),
        'annual_savings_cny': round(savings_cny, 0),
    })


@app.route('/api/cluster/ring')
def hash_ring():
    """Get hash ring configuration"""
    return jsonify(CLUSTER_STATE['sharding'])


# =============================================================================
# Node API
# =============================================================================

@app.route('/api/nodes')
def list_nodes():
    """List all nodes"""
    role = request.args.get('role')

    nodes = list(CLUSTER_STATE['nodes'].values())
    if role:
        nodes = [n for n in nodes if n['role'] == role]

    return jsonify(nodes)


@app.route('/api/nodes/<node_id>')
def get_node(node_id):
    """Get node details"""
    if node_id not in CLUSTER_STATE['nodes']:
        return jsonify({'error': 'Node not found'}), 404

    return jsonify(CLUSTER_STATE['nodes'][node_id])


@app.route('/api/nodes', methods=['POST'])
def add_node():
    """Add a new node"""
    data = request.json
    node_id = data.get('node_id')

    if node_id in CLUSTER_STATE['nodes']:
        return jsonify({'error': 'Node ID already exists'}), 400

    CLUSTER_STATE['nodes'][node_id] = {
        'node_id': node_id,
        'role': data.get('role', 'scan_node'),
        'host': data.get('host'),
        'port': data.get('port', 9042),
        'state': 'active',
        'capacity': data.get('capacity', {}),
        'current_load': 0,
        'last_heartbeat': datetime.now().isoformat() + 'Z',
    }

    return jsonify({'node_id': node_id, 'status': 'added'})


@app.route('/api/nodes/<node_id>/heartbeat', methods=['POST'])
def node_heartbeat(node_id):
    """Update node heartbeat"""
    if node_id not in CLUSTER_STATE['nodes']:
        return jsonify({'error': 'Node not found'}), 404

    CLUSTER_STATE['nodes'][node_id]['last_heartbeat'] = datetime.now().isoformat() + 'Z'

    if 'load' in request.json:
        CLUSTER_STATE['nodes'][node_id]['current_load'] = request.json['load']

    return jsonify({'node_id': node_id, 'status': 'ok'})


# =============================================================================
# Task API
# =============================================================================

@app.route('/api/tasks')
def list_tasks():
    """List all tasks"""
    status = request.args.get('status')

    tasks = CLUSTER_STATE['tasks']
    if status:
        tasks = [t for t in tasks if t['status'] == status]

    return jsonify(tasks)


@app.route('/api/tasks/<task_id>')
def get_task(task_id):
    """Get task details"""
    task = next((t for t in CLUSTER_STATE['tasks'] if t['task_id'] == task_id), None)

    if not task:
        return jsonify({'error': 'Task not found'}), 404

    return jsonify(task)


@app.route('/api/tasks', methods=['POST'])
def create_task():
    """Create a new scan task"""
    data = request.json
    task_id = f"task-{len(CLUSTER_STATE['tasks']) + 1:03d}"

    task = {
        'task_id': task_id,
        'path': data.get('path', '/data'),
        'node_id': None,
        'progress': 0,
        'status': 'pending',
        'created_at': datetime.now().isoformat() + 'Z',
    }

    CLUSTER_STATE['tasks'].append(task)
    return jsonify(task)


@app.route('/api/tasks/<task_id>/start', methods=['POST'])
def start_task(task_id):
    """Start a task"""
    task = next((t for t in CLUSTER_STATE['tasks'] if t['task_id'] == task_id), None)

    if not task:
        return jsonify({'error': 'Task not found'}), 404

    # Assign to node with lowest load
    nodes = [n for n in CLUSTER_STATE['nodes'].values() if n['role'] == 'scan_node']
    nodes.sort(key=lambda x: x['current_load'])

    if nodes:
        task['node_id'] = nodes[0]['node_id']
        nodes[0]['current_load'] += 10

    task['status'] = 'running'
    return jsonify(task)


@app.route('/api/tasks/<task_id>/pause', methods=['POST'])
def pause_task(task_id):
    """Pause a task"""
    task = next((t for t in CLUSTER_STATE['tasks'] if t['task_id'] == task_id), None)

    if not task:
        return jsonify({'error': 'Task not found'}), 404

    task['status'] = 'paused'
    return jsonify(task)


# =============================================================================
# Sharding API
# =============================================================================

@app.route('/api/sharding/lookup', methods=['POST'])
def lookup_fingerprint():
    """Lookup fingerprint routing"""
    data = request.json
    fingerprint = data.get('fingerprint', '')

    # Compute hash
    hash_val = int(hashlib.md5(fingerprint.encode()).hexdigest()[:8], 16)
    shard_idx = hash_val % 256

    # Find routing
    ring = CLUSTER_STATE['sharding']['ring']
    for segment in ring:
        if segment['start'] <= shard_idx <= segment['end']:
            return jsonify({
                'fingerprint': fingerprint[:32],
                'shard': shard_idx,
                'primary': segment['primary'],
                'replicas': segment['replicas'],
            })

    return jsonify({'error': 'Routing not found'}), 500


# =============================================================================
# Analytics API
# =============================================================================

@app.route('/api/analytics/stats')
def analytics_stats():
    """Get storage analytics"""
    stats = CLUSTER_STATE['stats']

    return jsonify({
        'total_files': stats['total_files'],
        'total_chunks': stats['total_chunks'],
        'unique_chunks': stats['unique_chunks'],
        'duplicate_chunks': stats['duplicate_chunks'],
        'dedup_ratio': round(stats['dedup_ratio'] * 100, 1),
        'original_tb': round(stats['original_bytes'] / 1024**4, 2),
        'stored_tb': round(stats['stored_bytes'] / 1024**4, 2),
        'savings_tb': round((stats['original_bytes'] - stats['stored_bytes']) / 1024**4, 2),
    })


@app.route('/api/analytics/shards')
def shard_stats():
    """Get per-shard statistics"""
    # Generate mock shard stats
    shards = []
    for i in range(4):
        base = 1000000 + random.randint(-100000, 100000)
        shards.append({
            'shard_id': f'shard-{i}',
            'fingerprints': base,
            'size_gb': 150 + random.randint(-10, 20),
        })

    return jsonify(shards)


# =============================================================================
# Health Check
# =============================================================================

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })


# =============================================================================
# Main
# =============================================================================

def main():
    print("="*70)
    print("Distributed Storage System - Web Console")
    print("="*70)
    print(f"\nNodes: {len(CLUSTER_STATE['nodes'])}")
    print(f"Tasks: {len(CLUSTER_STATE['tasks'])}")
    print(f"Shards: {CLUSTER_STATE['sharding']['total_shards']}")
    print("\nStarting server on http://localhost:5001")
    print("Open http://localhost:5001 in your browser")
    print("="*70)

    app.run(host='0.0.0.0', port=5001, debug=True)


if __name__ == '__main__':
    main()
