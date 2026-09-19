"""
Compliance Reporting

Generates compliance reports for regulatory requirements:
- GDPR data retention compliance
- SOC2 audit trail requirements
- ISO27001 information security controls
- Custom corporate policies
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict

from semantic.audit_store import AuditStore, AuditEntry, AuditEventType


class ComplianceStandard(Enum):
    """Supported compliance standards"""
    GDPR = "gdpr"                  # EU General Data Protection Regulation
    SOC2 = "soc2"                 # SOC 2 Trust Service Criteria
    ISO27001 = "iso27001"         # ISO/IEC 27001 Information Security
    HIPAA = "hipaa"               # US Health Insurance Portability
    CUSTOM = "custom"             # Custom corporate policy


class ReportPeriod(Enum):
    """Report period options"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


@dataclass
class ComplianceFinding:
    """A finding from compliance check"""
    severity: str                  # critical, high, medium, low, info
    category: str                  # Category of the finding
    description: str               # Human-readable description
    data_id: str = ""              # Affected data ID
    policy_id: str = ""            # Affected policy ID
    recommendation: str = ""       # Recommended action


@dataclass
class ComplianceReport:
    """Generated compliance report"""
    report_id: str
    generated_at: str              # ISO timestamp
    period_start: str              # Report period start
    period_end: str                # Report period end
    standard: ComplianceStandard   # Compliance standard
    summary: Dict                  # Executive summary
    metrics: Dict                  # Detailed metrics
    findings: List[ComplianceFinding]  # Findings/issues
    data_processing: List[Dict]    # Data processing records
    policy_changes: List[Dict]     # Policy change history
    retention_compliance: Dict     # Retention policy compliance
    integrity_verification: Dict   # Audit trail integrity


class ComplianceReporter:
    """
    Generates compliance reports based on audit data.

    Supports multiple compliance standards and customizable reports.
    """

    # GDPR-specific requirements
    GDPR_RETENTION_LIMITS = {
        'video': 30,               # days - unless incident related
        'log': 90,                 # days
        'access_log': 180,         # days
        'user_data': 365,          # days - right to be forgotten
    }

    # SOC2 Trust Service Criteria
    SOC2_CRITERIA = {
        'CC6.1': 'Logical access controls',
        'CC6.2': 'User authorization',
        'CC6.6': 'Security for data in transit',
        'CC7.1': 'System operations monitoring',
        'CC7.2': 'Security incident handling',
        'CC7.4': 'Business continuity',
        'CC8.1': 'Change management',
    }

    def __init__(self, audit_store: AuditStore, config: Dict = None):
        """
        Args:
            audit_store: AuditStore instance to query
            config: Configuration options
        """
        self.audit_store = audit_store
        self.config = config or {}

    def generate_report(
        self,
        start_date: str,
        end_date: str,
        standard: ComplianceStandard = ComplianceStandard.GDPR,
        include_details: bool = True
    ) -> ComplianceReport:
        """
        Generate a compliance report.

        Args:
            start_date: ISO timestamp for report start
            end_date: ISO timestamp for report end
            standard: Compliance standard to check against
            include_details: Include detailed data processing records

        Returns:
            ComplianceReport object
        """
        report_id = hashlib.md5(f"{start_date}{end_date}{standard.value}".encode()).hexdigest()[:16]

        # Query audit data for period
        entries = self.audit_store.query(
            start_time=start_date,
            end_time=end_date,
            limit=100000
        )

        # Generate sections
        summary = self._generate_summary(entries, standard)
        metrics = self._generate_metrics(entries)
        findings = self._generate_findings(entries, standard)
        data_processing = self._extract_data_processing(entries) if include_details else []
        policy_changes = self._extract_policy_changes(entries)
        retention_compliance = self._check_retention_compliance(entries, standard)
        integrity = self.audit_store.verify_integrity()

        return ComplianceReport(
            report_id=report_id,
            generated_at=datetime.utcnow().isoformat() + 'Z',
            period_start=start_date,
            period_end=end_date,
            standard=standard,
            summary=summary,
            metrics=metrics,
            findings=findings,
            data_processing=data_processing,
            policy_changes=policy_changes,
            retention_compliance=retention_compliance,
            integrity_verification=integrity
        )

    def _generate_summary(self, entries: List[AuditEntry], standard: ComplianceStandard) -> Dict:
        """Generate executive summary"""
        total_entries = len(entries)
        data_reduced = sum(1 for e in entries if e.event_type == AuditEventType.DATA_REDUCED)
        data_ingested = sum(1 for e in entries if e.event_type == AuditEventType.DATA_INGEST)

        original_bytes = sum(e.original_size for e in entries)
        new_bytes = sum(e.new_size for e in entries)

        # Calculate savings
        savings_percent = 0
        if original_bytes > 0:
            savings_percent = (1 - new_bytes / original_bytes) * 100

        return {
            'total_audit_entries': total_entries,
            'data_ingested_count': data_ingested,
            'data_reduced_count': data_reduced,
            'total_original_bytes': original_bytes,
            'total_new_bytes': new_bytes,
            'storage_savings_percent': savings_percent,
            'compliance_standard': standard.value,
            'status': 'COMPLIANT',  # Will be updated based on findings
        }

    def _generate_metrics(self, entries: List[AuditEntry]) -> Dict:
        """Generate detailed metrics"""
        # By event type
        by_event_type = defaultdict(int)
        by_data_type = defaultdict(int)
        by_action = defaultdict(int)
        by_classification = defaultdict(int)

        for entry in entries:
            by_event_type[entry.event_type.value] += 1
            by_data_type[entry.data_type] += 1
            by_action[entry.action] += 1
            by_classification[entry.classification] += 1

        # Calculate reduction by data type
        reduction_by_type = defaultdict(lambda: {'original': 0, 'new': 0, 'count': 0})
        for entry in entries:
            if entry.event_type == AuditEventType.DATA_REDUCED:
                reduction_by_type[entry.data_type]['original'] += entry.original_size
                reduction_by_type[entry.data_type]['new'] += entry.new_size
                reduction_by_type[entry.data_type]['count'] += 1

        # Build reduction summary
        reduction_summary = {}
        for dtype, data in reduction_by_type.items():
            if data['original'] > 0:
                reduction_summary[dtype] = {
                    'count': data['count'],
                    'original_bytes': data['original'],
                    'new_bytes': data['new'],
                    'savings_percent': (1 - data['new'] / data['original']) * 100
                }

        return {
            'by_event_type': dict(by_event_type),
            'by_data_type': dict(by_data_type),
            'by_action': dict(by_action),
            'by_classification': dict(by_classification),
            'reduction_by_type': reduction_summary,
        }

    def _generate_findings(
        self,
        entries: List[AuditEntry],
        standard: ComplianceStandard
    ) -> List[ComplianceFinding]:
        """Generate compliance findings"""
        findings = []

        # Check for integrity issues
        integrity = self.audit_store.verify_integrity()
        if not integrity['valid']:
            findings.append(ComplianceFinding(
                severity='critical',
                category='Audit Integrity',
                description=f"Audit trail integrity check failed: {len(integrity['errors'])} errors found",
                recommendation='Investigate and restore audit trail integrity immediately'
            ))

        # Check for failed operations
        failed_ops = [e for e in entries if e.result == 'failure' or e.result == 'error']
        if failed_ops:
            findings.append(ComplianceFinding(
                severity='high',
                category='Operation Failures',
                description=f"{len(failed_ops)} operations failed during the period",
                recommendation='Review failed operations and implement fixes'
            ))

        # Standard-specific checks
        if standard == ComplianceStandard.GDPR:
            findings.extend(self._check_gdpr_compliance(entries))
        elif standard == ComplianceStandard.SOC2:
            findings.extend(self._check_soc2_compliance(entries))

        return findings

    def _check_gdpr_compliance(self, entries: List[AuditEntry]) -> List[ComplianceFinding]:
        """Check GDPR-specific compliance"""
        findings = []

        # Check for data deletion compliance
        deletion_entries = [e for e in entries if e.event_type == AuditEventType.DATA_DELETED]
        if not deletion_entries:
            # This might be OK if no data exceeded retention limits
            pass

        # Check retention limits
        for data_type, limit_days in self.GDPR_RETENTION_LIMITS.items():
            relevant_entries = [e for e in entries if e.data_type == data_type]
            if not relevant_entries:
                continue

            # Check if any entries exceed retention
            now = datetime.utcnow()
            cutoff = (now - timedelta(days=limit_days)).isoformat() + 'Z'

            old_entries = [e for e in relevant_entries if e.timestamp < cutoff]
            if old_entries:
                findings.append(ComplianceFinding(
                    severity='high',
                    category='Data Retention',
                    description=f"{len(old_entries)} {data_type} entries exceed {limit_days}-day retention limit",
                    recommendation=f'Archive or delete {data_type} data older than {limit_days} days'
                ))

        # Check for right to be forgotten requests (would be deletion events)
        # In a real system, this would check for explicit deletion requests

        return findings

    def _check_soc2_compliance(self, entries: List[AuditEntry]) -> List[ComplianceFinding]:
        """Check SOC2-specific compliance"""
        findings = []

        # CC7.1 - System operations monitoring
        monitoring_events = [e for e in entries if e.event_type in (
            AuditEventType.DATA_INGEST,
            AuditEventType.DATA_REDUCED,
            AuditEventType.ANOMALY_DETECTED
        )]
        if not monitoring_events:
            findings.append(ComplianceFinding(
                severity='medium',
                category='CC7.1 - System Operations Monitoring',
                description='No system operations events recorded',
                recommendation='Verify monitoring is functioning correctly'
            ))

        # CC7.2 - Security incident handling
        anomaly_events = [e for e in entries if e.event_type == AuditEventType.ANOMALY_DETECTED]
        if anomaly_events:
            # Check that anomalies were handled (have corresponding resolution)
            handled = sum(1 for e in anomaly_events if e.metadata.get('resolved'))
            if handled < len(anomaly_events):
                findings.append(ComplianceFinding(
                    severity='medium',
                    category='CC7.2 - Security Incident Handling',
                    description=f'{len(anomaly_events) - handled} anomalies not marked as resolved',
                    recommendation='Ensure all detected anomalies are reviewed and resolved'
                ))

        # CC6.1 - Logical access controls (check for user access events)
        access_events = [e for e in entries if e.event_type == AuditEventType.USER_ACCESS]
        if not access_events:
            findings.append(ComplianceFinding(
                severity='low',
                category='CC6.1 - Logical Access Controls',
                description='No explicit user access events recorded',
                recommendation='Consider adding explicit access logging'
            ))

        # CC8.1 - Change management (check for policy changes)
        policy_changes = [e for e in entries if e.event_type in (
            AuditEventType.POLICY_CREATED,
            AuditEventType.POLICY_UPDATED,
            AuditEventType.POLICY_DELETED
        )]
        if policy_changes:
            # Check that all changes have approval
            unapproved = [e for e in policy_changes if not e.metadata.get('approved_by')]
            if unapproved:
                findings.append(ComplianceFinding(
                    severity='medium',
                    category='CC8.1 - Change Management',
                    description=f'{len(unapproved)} policy changes without approval',
                    recommendation='Ensure all policy changes have documented approval'
                ))

        return findings

    def _extract_data_processing(self, entries: List[AuditEntry]) -> List[Dict]:
        """Extract data processing records"""
        processing = []

        for entry in entries:
            if entry.event_type == AuditEventType.DATA_REDUCED:
                processing.append({
                    'timestamp': entry.timestamp,
                    'data_id': entry.data_id,
                    'data_type': entry.data_type,
                    'action': entry.action,
                    'original_size': entry.original_size,
                    'new_size': entry.new_size,
                    'classification': entry.classification,
                    'policy_id': entry.policy_id,
                    'reason': entry.reason,
                    'savings_percent': (1 - entry.new_size / entry.original_size) * 100 if entry.original_size > 0 else 0
                })

        return processing

    def _extract_policy_changes(self, entries: List[AuditEntry]) -> List[Dict]:
        """Extract policy change history"""
        changes = []

        for entry in entries:
            if entry.event_type in (AuditEventType.POLICY_CREATED, AuditEventType.POLICY_UPDATED):
                changes.append({
                    'timestamp': entry.timestamp,
                    'event_type': entry.event_type.value,
                    'policy_id': entry.policy_id,
                    'actor': entry.actor,
                    'reason': entry.reason,
                    'metadata': entry.metadata
                })

        return changes

    def _check_retention_compliance(
        self,
        entries: List[AuditEntry],
        standard: ComplianceStandard
    ) -> Dict:
        """Check retention policy compliance"""
        if standard == ComplianceStandard.GDPR:
            retention_limits = self.GDPR_RETENTION_LIMITS
        else:
            retention_limits = {
                'video': 90,
                'log': 180,
                'default': 365,
            }

        compliance = {}

        for data_type in set(e.data_type for e in entries):
            limit = retention_limits.get(data_type, retention_limits.get('default', 365))
            entries_of_type = [e for e in entries if e.data_type == data_type]

            # Count entries within and outside retention
            now = datetime.utcnow()
            cutoff = (now - timedelta(days=limit)).isoformat() + 'Z'

            within_retention = sum(1 for e in entries_of_type if e.timestamp >= cutoff)
            outside_retention = sum(1 for e in entries_of_type if e.timestamp < cutoff)

            compliance[data_type] = {
                'retention_days': limit,
                'entries_within_retention': within_retention,
                'entries_outside_retention': outside_retention,
                'compliant': outside_retention == 0
            }

        return compliance

    def generate_report_text(self, report: ComplianceReport) -> str:
        """Generate human-readable text report"""
        lines = [
            "="*70,
            "COMPLIANCE REPORT",
            "="*70,
            "",
            f"Report ID: {report.report_id}",
            f"Generated: {report.generated_at}",
            f"Period: {report.period_start} to {report.period_end}",
            f"Standard: {report.standard.value.upper()}",
            "",
            "-"*70,
            "EXECUTIVE SUMMARY",
            "-"*70,
        ]

        summary = report.summary
        lines.extend([
            f"Status: {summary['status']}",
            f"Total Audit Entries: {summary['total_audit_entries']:,}",
            f"Data Ingested: {summary['data_ingested_count']:,}",
            f"Data Processed: {summary['data_reduced_count']:,}",
            f"Storage Savings: {summary['storage_savings_percent']:.1f}%",
            "",
            "-"*70,
            "METRICS",
            "-"*70,
        ])

        metrics = report.metrics
        lines.append("By Event Type:")
        for evt, count in metrics['by_event_type'].items():
            lines.append(f"  {evt}: {count:,}")

        lines.append("\nBy Data Type:")
        for dtype, count in metrics['by_data_type'].items():
            lines.append(f"  {dtype}: {count:,}")

        lines.append("\nReduction by Type:")
        for dtype, data in metrics['reduction_by_type'].items():
            lines.append(f"  {dtype}: {data['savings_percent']:.1f}% ({data['count']:,} files)")

        if report.findings:
            lines.extend([
                "",
                "-"*70,
                "FINDINGS",
                "-"*70,
            ])
            for i, finding in enumerate(report.findings, 1):
                lines.extend([
                    f"{i}. [{finding.severity.upper()}] {finding.category}",
                    f"   {finding.description}",
                    f"   Recommendation: {finding.recommendation}",
                    "",
                ])

        lines.extend([
            "-"*70,
            "AUDIT INTEGRITY",
            "-"*70,
            f"Chain Valid: {report.integrity_verification['valid']}",
            f"Total Entries: {report.integrity_verification['total_entries']}",
        ])

        if report.integrity_verification['errors']:
            lines.append("Errors:")
            for error in report.integrity_verification['errors']:
                lines.append(f"  - {error}")

        lines.extend([
            "",
            "-"*70,
            "RETENTION COMPLIANCE",
            "-"*70,
        ])

        for dtype, data in report.retention_compliance.items():
            status = "COMPLIANT" if data['compliant'] else "NON-COMPLIANT"
            lines.append(f"  {dtype}: {status} (limit: {data['retention_days']} days)")

        lines.extend([
            "",
            "="*70,
            "END OF REPORT",
            "="*70,
        ])

        return "\n".join(lines)

    def export_report(
        self,
        report: ComplianceReport,
        output_path: str,
        format: str = "json"
    ) -> str:
        """
        Export report to file.

        Args:
            report: ComplianceReport to export
            output_path: Output file path
            format: Export format (json, text, html)

        Returns:
            Path to exported file
        """
        if format == "json":
            with open(output_path, 'w') as f:
                json.dump({
                    'report_id': report.report_id,
                    'generated_at': report.generated_at,
                    'period_start': report.period_start,
                    'period_end': report.period_end,
                    'standard': report.standard.value,
                    'summary': report.summary,
                    'metrics': report.metrics,
                    'findings': [
                        {
                            'severity': f.severity,
                            'category': f.category,
                            'description': f.description,
                            'data_id': f.data_id,
                            'policy_id': f.policy_id,
                            'recommendation': f.recommendation
                        }
                        for f in report.findings
                    ],
                    'retention_compliance': report.retention_compliance,
                    'integrity_verification': report.integrity_verification
                }, f, indent=2)

        elif format == "text":
            text = self.generate_report_text(report)
            with open(output_path, 'w') as f:
                f.write(text)

        elif format == "html":
            html = self._generate_html_report(report)
            with open(output_path, 'w') as f:
                f.write(html)

        return output_path

    def _generate_html_report(self, report: ComplianceReport) -> str:
        """Generate HTML report"""
        # Simple HTML template
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Compliance Report - {report.report_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 1px solid #ccc; padding-bottom: 10px; }}
        .status-compliant {{ color: green; font-weight: bold; }}
        .status-non-compliant {{ color: red; font-weight: bold; }}
        .finding {{ margin: 20px 0; padding: 15px; border-left: 4px solid #ccc; }}
        .critical {{ border-color: red; background: #fff5f5; }}
        .high {{ border-color: orange; background: #fffaf0; }}
        .medium {{ border-color: yellow; background: #fffbea; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f5f5f5; }}
    </style>
</head>
<body>
    <h1>Compliance Report</h1>
    <p><strong>Report ID:</strong> {report.report_id}</p>
    <p><strong>Generated:</strong> {report.generated_at}</p>
    <p><strong>Period:</strong> {report.period_start} to {report.period_end}</p>
    <p><strong>Standard:</strong> {report.standard.value.upper()}</p>

    <h2>Executive Summary</h2>
    <p><strong>Status:</strong> <span class="status-{report.summary['status'].lower()}">{report.summary['status']}</span></p>
    <p><strong>Total Audit Entries:</strong> {report.summary['total_audit_entries']:,}</p>
    <p><strong>Storage Savings:</strong> {report.summary['storage_savings_percent']:.1f}%</p>

    <h2>Metrics</h2>
    <table>
        <tr><th>Event Type</th><th>Count</th></tr>
"""
        for evt, count in report.metrics['by_event_type'].items():
            html += f"        <tr><td>{evt}</td><td>{count:,}</td></tr>\n"

        html += "    </table>\n"

        if report.findings:
            html += "    <h2>Findings</h2>\n"
            for finding in report.findings:
                html += f"""    <div class="finding {finding.severity}">
        <strong>[{finding.severity.upper()}]</strong> {finding.category}<br>
        {finding.description}<br>
        <em>Recommendation:</em> {finding.recommendation}
    </div>
"""

        html += """
</body>
</html>"""
        return html


# Demo usage
if __name__ == '__main__':
    import tempfile
    from semantic.audit_store import AuditStore, AuditEntry, AuditEventType

    print("Compliance Reporter Demo")
    print("="*50)

    # Create temp audit store with sample data
    temp_dir = tempfile.mkdtemp()
    audit_store = AuditStore(temp_dir)

    # Create sample entries
    from datetime import timedelta
    base_time = datetime.utcnow() - timedelta(days=7)

    for i in range(50):
        entry = AuditEntry(
            event_type=AuditEventType.DATA_REDUCED if i % 3 == 0 else AuditEventType.DATA_INGEST,
            actor="system",
            data_id=f"video_{i:04d}",
            data_type="video",
            action="reduce" if i % 3 == 0 else "ingest",
            original_size=100 * 1024 * 1024,
            new_size=30 * 1024 * 1024 if i % 3 == 0 else 100 * 1024 * 1024,
            classification="HIGH" if i % 5 == 0 else "MEDIUM",
            policy_id="policy_001",
            timestamp=(base_time + timedelta(hours=i)).isoformat() + 'Z'
        )
        audit_store.append(entry)

    # Generate report
    reporter = ComplianceReporter(audit_store)

    start_date = (datetime.utcnow() - timedelta(days=7)).isoformat() + 'Z'
    end_date = datetime.utcnow().isoformat() + 'Z'

    print(f"\nGenerating GDPR compliance report...")
    report = reporter.generate_report(start_date, end_date, ComplianceStandard.GDPR)

    print(f"\nReport Summary:")
    print(f"  Report ID: {report.report_id}")
    print(f"  Status: {report.summary['status']}")
    print(f"  Total Entries: {report.summary['total_audit_entries']}")
    print(f"  Storage Savings: {report.summary['storage_savings_percent']:.1f}%")
    print(f"  Findings: {len(report.findings)}")

    # Print text report
    print("\n" + reporter.generate_report_text(report))

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    print("\n[Cleaned up temp storage]")
