# -*- coding: utf-8 -*-
"""
Compliance and Audit System Demo

Demonstrates:
1. Immutable audit trail with hash chain
2. Compliance report generation (GDPR, SOC2)
3. Policy versioning and lifecycle management
4. Retention policy compliance checking
"""

import random
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic.audit_store import AuditStore, AuditEntry, AuditEventType
from semantic.compliance_reporter import ComplianceReporter, ComplianceStandard
from semantic.policy_manager import PolicyManager, PolicyStatus
from semantic_reducer import AuditLogger


def demo_audit_store():
    """Demo: Immutable audit storage with hash chain"""
    print("\n" + "="*70)
    print("Immutable Audit Storage Demo")
    print("="*70)

    # Create temp storage
    temp_dir = tempfile.mkdtemp()
    store = AuditStore(temp_dir)

    print(f"\n[1] Creating audit entries with hash chain...")

    # Simulate processing events
    events = [
        (AuditEventType.DATA_INGEST, "video_001", "video", "ingest", 100 * 1024 * 1024, 100 * 1024 * 1024),
        (AuditEventType.DATA_REDUCED, "video_001", "video", "downsample", 100 * 1024 * 1024, 10 * 1024 * 1024),
        (AuditEventType.DATA_INGEST, "log_001", "log", "ingest", 50 * 1024 * 1024, 50 * 1024 * 1024),
        (AuditEventType.DATA_REDUCED, "log_001", "log", "sample", 50 * 1024 * 1024, 5 * 1024 * 1024),
        (AuditEventType.ANOMALY_DETECTED, "video_002", "video", "error_burst", 0, 0),
    ]

    for i, (event_type, data_id, data_type, action, orig_size, new_size) in enumerate(events):
        entry = AuditEntry(
            event_type=event_type,
            actor="system",
            data_id=data_id,
            data_type=data_type,
            action=action,
            original_size=orig_size,
            new_size=new_size,
            classification="HIGH" if "video" in data_id else "MEDIUM",
            reason=f"{action} for {data_id}"
        )
        entry_id = store.append(entry)
        print(f"  Entry {i+1}: {event_type.value} - {entry_id[:8]}...")

    print(f"\n[2] Verifying hash chain integrity...")
    result = store.verify_integrity()
    print(f"  Chain Valid: {result['valid']}")
    print(f"  Total Entries: {result['total_entries']}")
    print(f"  First Entry: {result['first_entry']}")
    print(f"  Last Entry: {result['last_entry']}")

    print(f"\n[3] Querying audit entries...")
    all_entries = store.query(limit=10)
    print(f"  Total entries: {len(all_entries)}")
    for e in all_entries[:3]:
        print(f"    [{e.timestamp}] {e.event_type.value}: {e.action}")

    print(f"\n[4] Getting statistics...")
    stats = store.get_stats()
    print(f"  By Event Type: {stats['by_event_type']}")
    print(f"  Total Original: {stats['total_original_bytes'] / 1024 / 1024:.2f} MB")
    print(f"  Total New: {stats['total_new_bytes'] / 1024 / 1024:.2f} MB")

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    print("\n[Cleaned up temp storage]")


def demo_compliance_reporter():
    """Demo: Compliance report generation"""
    print("\n" + "="*70)
    print("Compliance Report Generation Demo")
    print("="*70)

    # Create temp audit store with sample data
    temp_dir = tempfile.mkdtemp()
    audit_store = AuditStore(temp_dir)

    print(f"\n[1] Generating sample audit data for 30 days...")

    # Generate 30 days of sample data
    base_time = datetime.utcnow() - timedelta(days=30)

    for day in range(30):
        # Daily ingestion
        for _ in range(random.randint(5, 20)):
            entry = AuditEntry(
                event_type=AuditEventType.DATA_INGEST,
                actor="system",
                data_id=f"video_{day:03d}_{random.randint(1, 100)}",
                data_type="video",
                action="ingest",
                original_size=random.randint(50, 200) * 1024 * 1024,
                new_size=random.randint(50, 200) * 1024 * 1024,
                classification=random.choice(["HIGH", "MEDIUM", "LOW"]),
                timestamp=(base_time + timedelta(days=day, hours=random.randint(0, 23))).isoformat() + 'Z'
            )
            audit_store.append(entry)

        # Daily reductions (80% of ingested gets reduced)
        for _ in range(random.randint(4, 16)):
            orig = random.randint(50, 200) * 1024 * 1024
            reduced = orig * random.uniform(0.05, 0.3)
            entry = AuditEntry(
                event_type=AuditEventType.DATA_REDUCED,
                actor="semantic_reducer",
                data_id=f"video_{day:03d}_{random.randint(1, 100)}",
                data_type="video",
                action="downsample",
                original_size=orig,
                new_size=int(reduced),
                classification="LOW",
                policy_id="policy_001",
                timestamp=(base_time + timedelta(days=day, hours=random.randint(0, 23))).isoformat() + 'Z'
            )
            audit_store.append(entry)

        # Random anomalies (every few days)
        if random.random() < 0.1:
            entry = AuditEntry(
                event_type=AuditEventType.ANOMALY_DETECTED,
                actor="system",
                data_id=f"video_{day:03d}_{random.randint(1, 100)}",
                data_type="video",
                action="error_burst",
                metadata={'resolved': random.choice([True, False])},
                timestamp=(base_time + timedelta(days=day, hours=random.randint(0, 23))).isoformat() + 'Z'
            )
            audit_store.append(entry)

    print(f"  Generated {audit_store.get_stats()['total_entries']} audit entries")

    print(f"\n[2] Generating GDPR Compliance Report...")
    reporter = ComplianceReporter(audit_store)

    start_date = (datetime.utcnow() - timedelta(days=30)).isoformat() + 'Z'
    end_date = datetime.utcnow().isoformat() + 'Z'

    gdpr_report = reporter.generate_report(start_date, end_date, ComplianceStandard.GDPR)

    print(f"\n  Report ID: {gdpr_report.report_id}")
    print(f"  Status: {gdpr_report.summary['status']}")
    print(f"  Total Audit Entries: {gdpr_report.summary['total_audit_entries']:,}")
    print(f"  Storage Savings: {gdpr_report.summary['storage_savings_percent']:.1f}%")
    print(f"  Findings: {len(gdpr_report.findings)}")

    print(f"\n[3] Report Details:")
    print(f"  By Event Type: {list(gdpr_report.metrics['by_event_type'].keys())}")
    print(f"  Reduction by Type: {list(gdpr_report.metrics['reduction_by_type'].keys())}")

    if gdpr_report.findings:
        print(f"\n  Findings:")
        for f in gdpr_report.findings[:3]:
            print(f"    - [{f.severity}] {f.category}: {f.description[:50]}...")

    print(f"\n[4] Retention Compliance:")
    for dtype, data in gdpr_report.retention_compliance.items():
        status = "OK" if data['compliant'] else "EXCEEDED"
        print(f"    {dtype}: {data['entries_within_retention']} within, {data['entries_outside_retention']} outside ({data['retention_days']} day limit) [{status}]")

    print(f"\n[5] Generating SOC2 Report...")
    soc2_report = reporter.generate_report(start_date, end_date, ComplianceStandard.SOC2)
    print(f"  Status: {soc2_report.summary['status']}")
    print(f"  Findings: {len(soc2_report.findings)}")

    # Print full text report
    print(f"\n[6] Sample Text Report (excerpt):")
    text_report = reporter.generate_report_text(gdpr_report)
    lines = text_report.split('\n')
    for line in lines[:40]:
        print(f"  {line}")

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    print("\n[Cleaned up temp storage]")


def demo_policy_manager():
    """Demo: Policy lifecycle management"""
    print("\n" + "="*70)
    print("Policy Lifecycle Management Demo")
    print("="*70)

    # Create temp storage
    temp_dir = tempfile.mkdtemp()
    manager = PolicyManager(temp_dir)

    print(f"\n[1] Available Policy Templates:")
    templates = ['surveillance_indoor', 'surveillance_parking', 'log_application', 'log_access']
    for t in templates:
        print(f"    - {t}")

    print(f"\n[2] Creating policy from template...")
    policy = manager.create_from_template(
        'surveillance_indoor',
        'Corporate Office Camera Policy',
        'security_admin'
    )
    print(f"  Policy ID: {policy.policy_id}")
    print(f"  Version: {policy.version_number}")
    print(f"  Status: {policy.status.value}")
    print(f"  Config: preserve_with_faces={policy.config.get('preserve_with_faces')}")

    print(f"\n[3] Activating policy...")
    active = manager.activate_policy(policy.policy_id, 'security_admin')
    print(f"  Status: {active.status.value}")

    print(f"\n[4] Updating policy (v2)...")
    v2 = manager.update_policy(
        policy.policy_id,
        {'preserve_with_vehicles': True, 'retain_days_high': 180},
        'security_admin',
        'Added vehicle preservation, extended high-priority retention'
    )
    print(f"  New Version: {v2.version_number}")

    print(f"\n[5] Suspending policy...")
    suspended = manager.suspend_policy(policy.policy_id, 'security_admin', 'Under maintenance')
    print(f"  Status: {suspended.status.value}")

    print(f"\n[6] Policy version history:")
    for v in manager.get_policy_history(policy.policy_id):
        print(f"    v{v.version_number}: {v.change_summary} ({v.created_at[:10]})")

    print(f"\n[7] Rollback to v1...")
    rolled = manager.rollback_policy(policy.policy_id, 1, 'security_admin', 'Restore original config')
    print(f"  New Version: {rolled.version_number} (copied from v1)")

    print(f"\n[8] Listing all policies:")
    for p in manager.list_policies():
        print(f"    {p['policy_id']}: {p['name']} ({p['status']}) v{p['current_version']}")

    print(f"\n[9] Validating policy configuration...")
    validation = manager.validate_policy(
        {'name': 'Test', 'preserve_with_faces': True},
        'surveillance'
    )
    print(f"  Valid: {validation['valid']}")

    validation_bad = manager.validate_policy(
        {'preserve_with_faces': 'yes'},  # Should be bool
        'surveillance'
    )
    print(f"  Invalid config test: {validation_bad['valid']} - {validation_bad['errors']}")

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    print("\n[Cleaned up temp storage]")


def demo_full_compliance_flow():
    """Demo: Complete compliance workflow"""
    print("\n" + "="*70)
    print("Complete Compliance Workflow Demo")
    print("="*70)

    # Setup
    temp_dir = tempfile.mkdtemp()
    audit_store = AuditStore(temp_dir + "/audit")
    policy_manager = PolicyManager(temp_dir + "/policies")

    print(f"\n[1] Setting up policies...")

    # Create surveillance policy
    surv_policy = policy_manager.create_from_template(
        'surveillance_indoor',
        'Primary Surveillance Policy',
        'admin'
    )
    policy_manager.activate_policy(surv_policy.policy_id, 'admin')

    # Create log policy
    log_policy = policy_manager.create_from_template(
        'log_application',
        'Application Log Policy',
        'admin'
    )
    policy_manager.activate_policy(log_policy.policy_id, 'admin')

    print(f"  Created {len(policy_manager.list_policies())} active policies")

    print(f"\n[2] Simulating 7 days of processing...")

    base_time = datetime.utcnow() - timedelta(days=7)

    # Simulate daily processing
    for day in range(7):
        for hour in range(24):
            timestamp = (base_time + timedelta(days=day, hours=hour)).isoformat() + 'Z'

            # Video ingestion
            entry = AuditEntry(
                event_type=AuditEventType.DATA_INGEST,
                actor="system",
                data_id=f"cam01_d{day:02d}h{hour:02d}",
                data_type="video",
                action="ingest",
                original_size=100 * 1024 * 1024,
                new_size=100 * 1024 * 1024,
                policy_id=surv_policy.policy_id,
                timestamp=timestamp
            )
            audit_store.append(entry)

            # Video reduction (if low value)
            if hour >= 2 and hour <= 5:  # Night - low value
                entry = AuditEntry(
                    event_type=AuditEventType.DATA_REDUCED,
                    actor="semantic_reducer",
                    data_id=f"cam01_d{day:02d}h{hour:02d}",
                    data_type="video",
                    action="downsample",
                    original_size=100 * 1024 * 1024,
                    new_size=10 * 1024 * 1024,
                    classification="LOW",
                    policy_id=surv_policy.policy_id,
                    timestamp=timestamp
                )
                audit_store.append(entry)

    print(f"  Processed {audit_store.get_stats()['total_entries']} audit entries")

    print(f"\n[3] Generating compliance report...")
    reporter = ComplianceReporter(audit_store)

    start_date = (datetime.utcnow() - timedelta(days=7)).isoformat() + 'Z'
    end_date = datetime.utcnow().isoformat() + 'Z'

    report = reporter.generate_report(start_date, end_date, ComplianceStandard.GDPR)

    print(f"\n  === COMPLIANCE REPORT ===")
    print(f"  Report ID: {report.report_id}")
    print(f"  Period: {report.period_start[:10]} to {report.period_end[:10]}")
    print(f"  Standard: GDPR")
    print(f"  Status: {report.summary['status']}")
    print(f"  ")
    print(f"  Total Entries: {report.summary['total_audit_entries']}")
    print(f"  Storage Savings: {report.summary['storage_savings_percent']:.1f}%")
    print(f"  ")
    print(f"  Findings: {len(report.findings)}")
    if report.findings:
        for f in report.findings:
            print(f"    - [{f.severity}] {f.category}")

    print(f"\n  === EXECUTIVE SUMMARY ===")
    print(f"  Data Ingested: {report.summary['data_ingested_count']} files")
    print(f"  Data Processed: {report.summary['data_reduced_count']} files")
    print(f"  Original Size: {report.summary['total_original_bytes'] / 1024 / 1024:.1f} MB")
    print(f"  Reduced Size: {report.summary['total_new_bytes'] / 1024 / 1024:.1f} MB")

    print(f"\n[4] Audit Trail Integrity: {'VALID' if report.integrity_verification['valid'] else 'INVALID'}")

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    print("\n[Cleaned up temp storage]")


def main():
    print("\n" + "#"*70)
    print("# Compliance and Audit System Demo")
    print("#"*70)
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*70)

    # Demo 1: Audit Store
    demo_audit_store()

    # Demo 2: Compliance Reporter
    demo_compliance_reporter()

    # Demo 3: Policy Manager
    demo_policy_manager()

    # Demo 4: Full Workflow
    demo_full_compliance_flow()

    print("\n" + "#"*70)
    print("# Demo Complete")
    print("#"*70)
    print("""
Components Demonstrated:
1. AuditStore - Immutable append-only storage with hash chain
2. ComplianceReporter - GDPR/SOC2 compliance reporting
3. PolicyManager - Policy versioning and lifecycle management

Next Steps:
1. Deploy audit store for production use
2. Configure automated compliance reports
3. Set up policy approval workflows
""")


if __name__ == '__main__':
    main()
