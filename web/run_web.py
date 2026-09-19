# -*- coding: utf-8 -*-
"""
Web Console Demo

Demonstrates the web management interface by:
1. Starting the Flask API server
2. Opening the browser
3. Running some sample operations
"""

import webbrowser
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic.audit_store import AuditStore, AuditEntry, AuditEventType
from semantic.policy_manager import PolicyManager
from semantic.log_analyzer import LogAnalyzer


def generate_sample_data():
    """Generate sample audit data for demo"""
    print("\n[1] Generating sample audit data...")

    # Create audit store
    audit_store = AuditStore("web_data/audit")

    # Generate 30 days of sample data
    base_time = datetime.now() - timedelta(days=30)

    # Sample events
    cameras = ['CAM-001', 'CAM-002', 'CAM-003', 'CAM-004', 'CAM-005']
    actions = ['ingest', 'downsample', 'archive', 'delete']

    for day in range(30):
        for hour in range(24):
            timestamp = (base_time + timedelta(days=day, hours=hour)).isoformat() + 'Z'

            # 3-8 events per hour
            for _ in range(3 + (hash(f"{day}{hour}") % 6)):
                cam_id = cameras[hash(f"{day}{hour}{_}") % len(cameras)]
                action = actions[hash(f"{day}{hour}{_}") % len(actions)]

                if action == 'ingest':
                    orig_size = 50 + (hash(cam_id) % 150) * 1024 * 1024
                    new_size = orig_size
                elif action == 'downsample':
                    orig_size = 50 + (hash(cam_id) % 150) * 1024 * 1024
                    new_size = orig_size * (0.05 + (hash(cam_id) % 30) / 100)
                elif action == 'archive':
                    orig_size = 50 + (hash(cam_id) % 150) * 1024 * 1024
                    new_size = orig_size * 0.2
                else:
                    orig_size = 50 + (hash(cam_id) % 150) * 1024 * 1024
                    new_size = 0

                entry = AuditEntry(
                    event_type=AuditEventType.DATA_INGEST if action == 'ingest' else AuditEventType.DATA_REDUCED,
                    actor='system',
                    data_id=f"{cam_id}_d{day:02d}h{hour:02d}",
                    data_type='video',
                    action=action,
                    original_size=orig_size,
                    new_size=new_size,
                    classification='HIGH' if hash(cam_id) % 3 == 0 else 'MEDIUM' if hash(cam_id) % 3 == 1 else 'LOW',
                    policy_id='policy_001',
                    timestamp=timestamp
                )
                audit_store.append(entry)

    stats = audit_store.get_stats()
    print(f"  Generated {stats['total_entries']} audit entries")
    print(f"  Total original: {stats['total_original_bytes'] / 1024 / 1024 / 1024:.2f} GB")
    print(f"  Total reduced: {stats['total_new_bytes'] / 1024 / 1024 / 1024:.2f} GB")


def create_sample_policies():
    """Create sample policies for demo"""
    print("\n[2] Creating sample policies...")

    policy_manager = PolicyManager("web_data/policies")

    # Create policies from templates
    policies = [
        ('surveillance_indoor', 'Office Building Policy'),
        ('surveillance_parking', 'Parking Lot Policy'),
        ('log_application', 'Application Log Policy'),
    ]

    for template, name in policies:
        version = policy_manager.create_from_template(template, name, 'setup_demo')
        policy_manager.activate_policy(version.policy_id, 'setup_demo')
        print(f"  Created: {name} (ID: {version.policy_id[:8]}...)")

    print(f"  Total policies: {len(policy_manager.list_policies())}")


def main():
    print("\n" + "="*70)
    print("Semantic Data Reduction Console - Web Demo")
    print("="*70)

    # Generate sample data
    generate_sample_data()

    # Create sample policies
    create_sample_policies()

    print("\n[3] Web Console Features:")
    print("  - Dashboard with real-time metrics")
    print("  - Policy management (create, edit, rollback)")
    print("  - Camera management")
    print("  - Audit log viewer with integrity verification")
    print("  - Compliance reporting (GDPR/SOC2)")
    print("  - ROI calculator")

    print("\n[4] Starting web server...")
    print("  URL: http://localhost:5000")
    print("  Press Ctrl+C to stop")

    # Open browser after a short delay
    time.sleep(1)
    webbrowser.open('http://localhost:5000')

    # Run Flask app
    from web.api import app
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    main()
