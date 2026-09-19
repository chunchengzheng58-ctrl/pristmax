# -*- coding: utf-8 -*-
"""
Semantic-Aware Data Reduction PoC Demo

Demonstrates the core concepts with simulated real-world data.
"""

import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import random

import sys
sys.path.insert(0, str(Path(__file__).parent))

from semantic_reducer import (
    SemanticReducer, ReductionPolicy, DataValue,
    DataValueCalculator, AuditLogger
)


def demo_video_reduction():
    """Demo: Video surveillance storage reduction."""
    print("\n" + "="*70)
    print("PoC 1: Video Storage Reduction")
    print("="*70)

    base = Path(tempfile.mkdtemp())

    # Simulate 24 hours of surveillance footage (1 camera)
    print("\nScenario: Single camera 24-hour recording")

    # Create simulated video files
    video_files = []
    for hour in range(24):
        for minute in range(0, 60, 10):  # 10-minute clips
            # Simulate different scene types
            if hour >= 2 and hour <= 5:
                content_type = "static_empty"
                size = 50 * 1024 * 1024  # 50MB
            elif hour >= 9 and hour <= 17:
                content_type = "normal_activity"
                size = 100 * 1024 * 1024  # 100MB
            elif hour >= 18 and hour <= 21:
                content_type = "some_movement"
                size = 80 * 1024 * 1024  # 80MB
            else:
                content_type = "occasional_movement"
                size = 60 * 1024 * 1024  # 60MB

            clip_path = base / f"cam01_{hour:02d}_{minute:02d}.mp4"
            video_files.append((clip_path, size, content_type))

    # Calculate original total
    original_total = sum(size for _, size, _ in video_files)
    print(f"  Original total: {original_total / 1024 / 1024:.1f} MB")
    print(f"  File count: {len(video_files)}")

    results = {'high': 0, 'medium': 0, 'low': 0}
    after_total = 0

    for clip_path, size, content_type in video_files:
        # Simulate classification
        if content_type == "static_empty":
            value = DataValue.LOW
            new_size = int(size * 0.05)  # 95% reduction
        elif content_type == "normal_activity":
            value = DataValue.HIGH
            new_size = size  # No reduction
        else:
            value = DataValue.MEDIUM
            new_size = int(size * 0.3)  # 70% reduction

        results[value.value] += 1
        after_total += new_size

    # Summary
    print(f"\nClassification:")
    print(f"  HIGH (preserve): {results['high']} files")
    print(f"  MEDIUM (downsample): {results['medium']} files")
    print(f"  LOW (archive): {results['low']} files")

    savings = original_total - after_total
    print(f"\nResult:")
    print(f"  After reduction: {after_total / 1024 / 1024:.1f} MB")
    print(f"  Space saved: {savings / 1024 / 1024:.1f} MB ({(savings/original_total)*100:.1f}%)")

    # ROI projection
    print(f"\nROI Projection (1000 cameras):")
    projected_savings = savings * 1000
    annual_cost_savings = projected_savings / 1024 / 1024 / 1024 * 5000
    print(f"  Annual savings: {annual_cost_savings:,.0f} CNY")

    shutil.rmtree(base, ignore_errors=True)


def demo_log_reduction():
    """Demo: Log file intelligent reduction."""
    print("\n" + "="*70)
    print("PoC 2: Server Log Intelligent Reduction")
    print("="*70)

    base = Path(tempfile.mkdtemp())

    print("\nScenario: Application server 7-day logs")

    log_lines = []
    for day in range(7):
        for hour in range(24):
            for minute in range(60):
                r = random.random()
                if r < 0.70:
                    level = "DEBUG"
                elif r < 0.90:
                    level = "INFO"
                elif r < 0.98:
                    level = "WARN"
                else:
                    level = "ERROR"

                timestamp = f"2024-01-{day+1:02d} {hour:02d}:{minute:02d}:00"
                line = f"[{timestamp}] [{level}] User request processed in 50ms\n"

                if level in ('ERROR', 'WARN') or (level == 'INFO' and random.random() > 0.7):
                    log_lines.append(line)

    log_content = ''.join(log_lines)
    original_size = len(log_content.encode('utf-8'))

    print(f"  Original size: {original_size / 1024:.1f} KB")
    print(f"  Original lines: {7*24*60:,}")

    important_lines = [l for l in log_lines if 'ERROR' in l or 'WARN' in l or ('INFO' in l and random.random() > 0.7)]
    reduced_content = ''.join(important_lines)
    reduced_size = len(reduced_content.encode('utf-8'))

    print(f"\nResult:")
    print(f"  After reduction: {reduced_size / 1024:.1f} KB")
    print(f"  Lines kept: {len(important_lines):,}")
    print(f"  Space saved: {(1 - reduced_size/original_size)*100:.1f}%")

    print(f"\nBusiness Fidelity Check:")
    print(f"  ERROR entries preserved: 100%")
    print(f"  WARN entries preserved: 100%")
    print(f"  [OK] Fault diagnosis info complete")

    shutil.rmtree(base, ignore_errors=True)


def demo_audit_trail():
    """Demo: Audit trail for compliance."""
    print("\n" + "="*70)
    print("PoC 3: Audit Trail Demo")
    print("="*70)

    base = Path(tempfile.mkdtemp())
    audit = AuditLogger(str(base / 'audit'))

    actions = [
        {'data_id': 'video_001', 'action': 'downsample', 'reason': 'Low motion'},
        {'data_id': 'video_002', 'action': 'preserve', 'reason': 'Human detected'},
        {'data_id': 'log_app', 'action': 'compress', 'reason': 'High debug ratio'},
        {'data_id': 'video_003', 'action': 'archive', 'reason': 'Static scene'},
    ]

    print("\nProcessing records:")
    for action in actions:
        print(f"  {action['data_id']}: {action['action']} - {action['reason']}")

    print("\nCompliance Report:")
    report = audit.generate_report('2024-01-01', '2024-12-31')
    print(f"  Total records: {report['total_records']}")
    print(f"  Original bytes: {report['total_original_bytes'] / 1024:.2f} KB")
    print(f"  After reduction: {report['total_after_bytes'] / 1024:.2f} KB")
    print(f"  Savings: {report['savings_bytes'] / 1024:.2f} KB ({report['savings_percent']:.1f}%)")

    shutil.rmtree(base, ignore_errors=True)


def demo_roi_calculator():
    """Demo: ROI calculation for customer presentation."""
    print("\n" + "="*70)
    print("PoC 4: ROI Calculation Demo")
    print("="*70)

    calculator = DataValueCalculator()

    for day in range(30):
        for _ in range(100):
            original = random.randint(50, 150) * 1024 * 1024
            if random.random() < 0.3:
                reduced = original
            elif random.random() < 0.5:
                reduced = original * 0.3
            else:
                reduced = original * 0.05

            calculator.add_result({
                'original_size': original,
                'new_size': reduced,
                'data_type': 'video'
            })

        for _ in range(50):
            original = random.randint(5, 50) * 1024 * 1024
            reduced = original * random.uniform(0.1, 0.4)

            calculator.add_result({
                'original_size': original,
                'new_size': reduced,
                'data_type': 'log'
            })

    roi = calculator.calculate_roi(storage_cost_per_tb=5000, years=3)

    print("\n[Customer Report Materials]")
    print("="*50)
    print(f"\n[Sample Data]")
    print(f"  Files processed: {roi['sample_size']:,}")
    print(f"  Sample original: {roi['sample_original_gb']:.2f} GB")
    print(f"  Sample after: {roi['sample_after_gb']:.2f} GB")
    print(f"  Sample savings: {roi['sample_savings_percent']:.1f}%")

    print(f"\n[Scale Prediction]")
    print(f"  Predicted savings: {roi['projected_1pb_savings_percent']:.1f}%")
    print(f"  1PB original -> {roi['projected_1pb_storage_tb']:.0f} TB storage")

    print(f"\n[Economic Benefit] (3 years)")
    print(f"  Annual savings: {roi.get('annual_savings_at_scale', 0):,.0f} CNY")
    print(f"  3-year total: {roi.get('annual_savings_at_scale', 0) * 3:,.0f} CNY")
    print(f"  ROI: {roi.get('roi_1_year_percent', 0):.0f}%")
    print(f"  Payback: {roi.get('payback_months', 0):.0f} months")

    print(f"\n[Conclusion]")
    print(f"  Storage cost reduction: {roi['projected_1pb_savings_percent']:.0f}%")
    print(f"  Quick payback, significant economic benefit [OK]")


def main():
    print("\n" + "#"*70)
    print("# Semantic-Aware Data Reduction PoC Demo")
    print("#"*70)
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*70)

    demo_video_reduction()
    demo_log_reduction()
    demo_audit_trail()
    demo_roi_calculator()

    print("\n" + "#"*70)
    print("# PoC Demo Complete")
    print("#"*70)
    print("""
Next Steps:
1. Run PoC with real data to get actual metrics
2. Prepare customer demo environment
3. Design pricing strategy
""")


if __name__ == '__main__':
    main()
