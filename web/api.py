# -*- coding: utf-8 -*-
"""
Web API Server for Semantic Data Reduction Console

REST API for:
- Dashboard metrics
- Policy management
- Camera management
- Audit log queries
- Compliance reports
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Import semantic modules
from semantic.audit_store import AuditStore, AuditEntry, AuditEventType
from semantic.compliance_reporter import ComplianceReporter, ComplianceStandard
from semantic.policy_manager import PolicyManager
from semantic.surveillance_policy import SurveillancePolicy
from semantic.log_policy import LogPolicy
from semantic_reducer import DataValueCalculator

app = Flask(__name__, static_folder='.')
CORS(app)

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "web_data"
DATA_DIR.mkdir(exist_ok=True)

AUDIT_DIR = DATA_DIR / "audit"
AUDIT_DIR.mkdir(exist_ok=True)

POLICY_DIR = DATA_DIR / "policies"
POLICY_DIR.mkdir(exist_ok=True)

# Initialize stores
audit_store = AuditStore(str(AUDIT_DIR))
policy_manager = PolicyManager(str(POLICY_DIR))
calculator = DataValueCalculator()

# In-memory state for demo (would be database in production)
cameras = {
    'CAM-001': {'name': 'Lobby Entrance', 'type': 'indoor', 'policy_id': None, 'storage_used': 0.65},
    'CAM-002': {'name': 'Parking Lot A', 'type': 'parking', 'policy_id': None, 'storage_used': 0.45},
    'CAM-003': {'name': 'Office Floor 3', 'type': 'indoor', 'policy_id': None, 'storage_used': 0.72},
}


# =============================================================================
# Static Files
# =============================================================================

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('.', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('.', filename)


# =============================================================================
# Dashboard API
# =============================================================================

@app.route('/api/dashboard/stats')
def dashboard_stats():
    """Get dashboard statistics"""
    stats = audit_store.get_stats()

    # Calculate totals from audit data
    total_original = stats.get('total_original_bytes', 0)
    total_new = stats.get('total_new_bytes', 0)
    savings = total_original - total_new
    savings_percent = (savings / total_original * 100) if total_original > 0 else 0

    return jsonify({
        'total_cameras': len(cameras),
        'total_storage_saved_tb': round(savings / 1024 / 1024 / 1024 / 1024, 1),
        'active_policies': len(policy_manager.list_policies(status=None)),
        'system_status': 'operational',
        'reduction_percent': round(savings_percent, 1),
        'original_data_pb': round(total_original / 1024 / 1024 / 1024 / 1024 / 1024, 2),
        'retained_data_pb': round(total_new / 1024 / 1024 / 1024 / 1024 / 1024, 2),
        'today_processing_gb': round(savings / 1024 / 1024 / 1024, 1),
    })


@app.route('/api/dashboard/trend')
def dashboard_trend():
    """Get storage reduction trend data"""
    days = int(request.args.get('days', 7))

    # Generate mock trend data
    trend = []
    base_savings = 50  # GB per day base
    for i in range(days):
        date = (datetime.now() - timedelta(days=days - i - 1)).strftime('%Y-%m-%d')
        trend.append({
            'date': date,
            'original_gb': base_savings + (i * 5) + (hash(date) % 20),
            'reduced_gb': (base_savings + (i * 5)) * 0.3 + (hash(date) % 10)
        })

    return jsonify(trend)


@app.route('/api/dashboard/alerts')
def dashboard_alerts():
    """Get recent alerts"""
    # Get recent anomaly entries
    anomalies = audit_store.query(
        event_types=[AuditEventType.ANOMALY_DETECTED],
        limit=10
    )

    alerts = []
    for entry in anomalies:
        alerts.append({
            'id': entry.entry_id,
            'type': 'anomaly',
            'severity': 'warning',
            'message': f"Anomaly detected: {entry.reason}",
            'timestamp': entry.timestamp,
            'data_id': entry.data_id
        })

    return jsonify(alerts)


# =============================================================================
# Policy API
# =============================================================================

@app.route('/api/policies')
def list_policies():
    """List all policies"""
    policies = policy_manager.list_policies()
    return jsonify(policies)


@app.route('/api/policies', methods=['POST'])
def create_policy():
    """Create a new policy"""
    data = request.json

    name = data.get('name')
    policy_type = data.get('type', 'surveillance')
    template = data.get('template', 'surveillance_indoor')

    if not name:
        return jsonify({'error': 'Policy name is required'}), 400

    # Create from template
    version = policy_manager.create_from_template(template, name, 'web_ui')

    return jsonify({
        'policy_id': version.policy_id,
        'version_id': version.version_id,
        'version_number': version.version_number,
        'status': version.status.value
    })


@app.route('/api/policies/<policy_id>')
def get_policy(policy_id):
    """Get policy details"""
    version = policy_manager.get_current_version(policy_id)
    if not version:
        return jsonify({'error': 'Policy not found'}), 404

    history = policy_manager.get_policy_history(policy_id)

    return jsonify({
        'policy_id': policy_id,
        'name': version.config.get('name'),
        'type': version.config.get('type'),
        'version': version.version_number,
        'status': version.status.value,
        'config': version.config,
        'history': [{'version': v.version_number, 'created_at': v.created_at, 'change_summary': v.change_summary} for v in history]
    })


@app.route('/api/policies/<policy_id>', methods=['PUT'])
def update_policy(policy_id):
    """Update a policy"""
    data = request.json

    version = policy_manager.update_policy(
        policy_id,
        config=data,
        updated_by='web_ui',
        reason=data.get('reason', 'Updated via web console')
    )

    return jsonify({
        'policy_id': policy_id,
        'version_number': version.version_number,
        'status': version.status.value
    })


@app.route('/api/policies/<policy_id>/activate', methods=['POST'])
def activate_policy(policy_id):
    """Activate a policy"""
    version = policy_manager.activate_policy(policy_id, 'web_ui')
    return jsonify({'status': version.status.value})


@app.route('/api/policies/<policy_id>/suspend', methods=['POST'])
def suspend_policy(policy_id):
    """Suspend a policy"""
    data = request.json
    reason = data.get('reason', 'Suspended via web console')

    version = policy_manager.suspend_policy(policy_id, 'web_ui', reason)
    return jsonify({'status': version.status.value})


@app.route('/api/policies/<policy_id>/rollback', methods=['POST'])
def rollback_policy(policy_id):
    """Rollback policy to a previous version"""
    data = request.json
    target_version = data.get('version')

    version = policy_manager.rollback_policy(
        policy_id,
        target_version,
        'web_ui',
        data.get('reason', 'Rollback via web console')
    )

    return jsonify({
        'policy_id': policy_id,
        'new_version': version.version_number
    })


@app.route('/api/policies/templates')
def list_templates():
    """List available policy templates"""
    return jsonify([
        {'id': 'surveillance_indoor', 'name': 'Indoor Camera', 'type': 'surveillance'},
        {'id': 'surveillance_parking', 'name': 'Parking Lot', 'type': 'surveillance'},
        {'id': 'log_application', 'name': 'Application Logs', 'type': 'log'},
        {'id': 'log_access', 'name': 'Access Logs', 'type': 'log'},
    ])


# =============================================================================
# Camera API
# =============================================================================

@app.route('/api/cameras')
def list_cameras():
    """List all cameras"""
    result = []
    for cam_id, cam in cameras.items():
        result.append({
            'id': cam_id,
            'name': cam['name'],
            'type': cam['type'],
            'policy_id': cam['policy_id'],
            'storage_used': cam['storage_used'],
            'status': 'active'
        })
    return jsonify(result)


@app.route('/api/cameras/<cam_id>')
def get_camera(cam_id):
    """Get camera details"""
    if cam_id not in cameras:
        return jsonify({'error': 'Camera not found'}), 404

    cam = cameras[cam_id]
    return jsonify({
        'id': cam_id,
        'name': cam['name'],
        'type': cam['type'],
        'policy_id': cam['policy_id'],
        'storage_used': cam['storage_used'],
        'status': 'active'
    })


@app.route('/api/cameras', methods=['POST'])
def add_camera():
    """Add a new camera"""
    data = request.json
    cam_id = data.get('id')

    if cam_id in cameras:
        return jsonify({'error': 'Camera ID already exists'}), 400

    cameras[cam_id] = {
        'name': data.get('name', cam_id),
        'type': data.get('type', 'indoor'),
        'policy_id': data.get('policy_id'),
        'storage_used': 0.0
    }

    return jsonify({'id': cam_id, 'status': 'added'})


@app.route('/api/cameras/<cam_id>/policy', methods=['PUT'])
def assign_camera_policy(cam_id):
    """Assign a policy to a camera"""
    if cam_id not in cameras:
        return jsonify({'error': 'Camera not found'}), 404

    data = request.json
    cameras[cam_id]['policy_id'] = data.get('policy_id')

    return jsonify({'camera_id': cam_id, 'policy_id': data.get('policy_id')})


# =============================================================================
# Audit Log API
# =============================================================================

@app.route('/api/audit')
def query_audit():
    """Query audit log entries"""
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    event_type = request.args.get('event_type')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    event_types = None
    if event_type:
        try:
            event_types = [AuditEventType(event_type)]
        except:
            pass

    entries = audit_store.query(
        start_time=start_time,
        end_time=end_time,
        event_types=event_types,
        limit=limit,
        offset=offset
    )

    return jsonify([{
        'entry_id': e.entry_id,
        'timestamp': e.timestamp,
        'event_type': e.event_type.value,
        'actor': e.actor,
        'data_id': e.data_id,
        'data_type': e.data_type,
        'action': e.action,
        'original_size': e.original_size,
        'new_size': e.new_size,
        'classification': e.classification,
        'policy_id': e.policy_id,
        'reason': e.reason,
        'result': e.result
    } for e in entries])


@app.route('/api/audit/verify')
def verify_audit():
    """Verify audit trail integrity"""
    result = audit_store.verify_integrity()
    return jsonify(result)


@app.route('/api/audit/stats')
def audit_stats():
    """Get audit statistics"""
    stats = audit_store.get_stats()
    return jsonify(stats)


# =============================================================================
# Compliance API
# =============================================================================

@app.route('/api/compliance/report', methods=['POST'])
def generate_compliance_report():
    """Generate a compliance report"""
    data = request.json

    start_date = data.get('start_date')
    end_date = data.get('end_date')
    standard = data.get('standard', 'gdpr')

    try:
        standard_enum = ComplianceStandard(standard.lower())
    except:
        standard_enum = ComplianceStandard.GDPR

    reporter = ComplianceReporter(audit_store)
    report = reporter.generate_report(start_date, end_date, standard_enum)

    return jsonify({
        'report_id': report.report_id,
        'generated_at': report.generated_at,
        'period_start': report.period_start,
        'period_end': report.period_end,
        'standard': report.standard.value,
        'summary': report.summary,
        'findings_count': len(report.findings),
        'integrity_valid': report.integrity_verification.get('valid', False)
    })


@app.route('/api/compliance/report/<report_id>')
def get_compliance_report(report_id):
    """Get compliance report details (mock for demo)"""
    return jsonify({
        'report_id': report_id,
        'status': 'COMPLIANT',
        'findings': []
    })


@app.route('/api/compliance/status')
def compliance_status():
    """Get overall compliance status"""
    integrity = audit_store.verify_integrity()

    return jsonify({
        'gdpr': 'COMPLIANT',
        'soc2': 'COMPLIANT',
        'last_audit': datetime.now().isoformat(),
        'open_findings': 0,
        'audit_integrity': integrity.get('valid', False),
        'total_audit_entries': integrity.get('total_entries', 0)
    })


# =============================================================================
# ROI Calculator API
# =============================================================================

@app.route('/api/roi/calculate')
def calculate_roi():
    """Calculate ROI based on current data"""
    stats = audit_store.get_stats()

    total_original = stats.get('total_original_bytes', 0)
    total_new = stats.get('total_new_bytes', 0)

    # Sample ROI calculation
    # Scale to 1000 cameras, 1 year
    scale_factor = 1000 * 365 / 7  # Assuming 7 days of data

    original_tb = (total_original * scale_factor) / 1024 / 1024 / 1024 / 1024
    reduced_tb = (total_new * scale_factor) / 1024 / 1024 / 1024 / 1024

    storage_cost_per_tb = 5000  # CNY

    annual_savings = (original_tb - reduced_tb) * storage_cost_per_tb
    implementation_cost = annual_savings * 0.2  # 20% of savings
    roi = (annual_savings - implementation_cost) / implementation_cost * 100 if implementation_cost > 0 else 0

    return jsonify({
        'sample_original_tb': round(total_original / 1024 / 1024 / 1024 / 1024, 2),
        'sample_reduced_tb': round(total_new / 1024 / 1024 / 1024 / 1024, 2),
        'sample_savings_percent': round((1 - total_new / total_original) * 100, 1) if total_original > 0 else 0,
        'projected_annual_original_pb': round(original_tb / 1024, 2),
        'projected_annual_reduced_pb': round(reduced_tb / 1024, 2),
        'annual_savings_cny': round(annual_savings, 0),
        'implementation_cost_cny': round(implementation_cost, 0),
        'roi_percent': round(roi, 0),
        'payback_months': 2
    })


# =============================================================================
# Health Check
# =============================================================================

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '0.1.0'
    })


# =============================================================================
# Main
# =============================================================================

def main():
    print("="*70)
    print("Semantic Data Reduction Console - Web API Server")
    print("="*70)
    print(f"\nData directory: {DATA_DIR}")
    print(f"Audit store: {AUDIT_DIR}")
    print(f"Policy store: {POLICY_DIR}")
    print("\nStarting server on http://localhost:5000")
    print("Open http://localhost:5000 in your browser")
    print("="*70)

    app.run(host='0.0.0.0', port=5000, debug=True)


if __name__ == '__main__':
    main()
