"""
CDC-Enabled Vault Integration Demo

Shows how CDC chunk-level deduplication integrates with the existing
vault workflow (fold -> catalog -> checkout -> release).

CDC provides maximum benefit for:
- Database dumps with minor version differences
- Log files with timestamps
- Versioned document backups
- VM images and disk clones
"""

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from storage_core import scan_local
from deep_archive_cdc import create_bundle_cdc, restore_bundle_cdc
from vault import Vault


def demo_cdc_vault():
    """Demo CDC integration with vault workflow."""

    print("="*70)
    print("CDC-Enabled Vault Workflow Demo")
    print("="*70)

    # Setup
    base = Path(tempfile.mkdtemp())
    vault_root = base / "vault"
    source_dir = base / "source"
    deliver_dir = base / "delivery"

    vault_root.mkdir()
    source_dir.mkdir()
    deliver_dir.mkdir()

    try:
        # Create test data simulating versioned backups
        print("\n1. Creating test data (simulating versioned backups)...")

        # Base content (common across versions)
        base_text = "=" * 1000 + "\n"
        base_text += "COMPANY BACKUP - CONFIDENTIAL\n" * 100
        base_text += "=" * 1000 + "\n"
        base_text += "Database dump content follows:\n"
        base_text += "CREATE TABLE users (id INT, name VARCHAR(100));\n" * 500
        base_text += "=" * 1000 + "\n"

        # Create 3 versions with minor differences
        versions = []
        for v in range(3):
            content = base_text
            if v > 0:
                # Insert version-specific changes
                content = content.replace(
                    "Database dump content follows:",
                    f"[VERSION {v}] Database changes applied:\n"
                    f"INSERT INTO users VALUES ({v}, 'user_{v}');\n"
                )
            content += f"\n[CHECKPOINT v{v} - Timestamp: 2024-01-{v+1:02d}]\n"

            file_path = source_dir / f"backup_v{v}.sql"
            file_path.write_text(content)
            versions.append(file_path)
            print(f"   Created: {file_path.name} ({len(content):,} bytes)")

        original_total = sum(v.stat().st_size for v in versions)
        print(f"   Total: {original_total:,} bytes")

        # Initialize vault
        print("\n2. Initializing vault...")
        vault = Vault(vault_root)

        # Fold with CDC
        print("\n3. Folding with CDC chunk-level deduplication...")
        record = vault.fold(source_dir)
        print(f"   Vault ID: {record['id']}")
        print(f"   Status: {record['status']}")
        print(f"   File count: {record['file_count']}")
        print(f"   Original bytes: {record['original_bytes']:,}")

        # Calculate actual archive size
        archive_path = vault.archive_path(record)
        archive_size = archive_path.stat().st_size
        print(f"   Archive size: {archive_size:,} bytes")
        print(f"   Space saved: {(1 - archive_size/original_total)*100:.1f}%")

        # Catalog
        print("\n4. Cataloging archive...")
        catalog = vault.catalog(record['id'])
        print(f"   Files in archive: {len(catalog['files'])}")
        print(f"   Verified: {catalog['verified']}")

        # Health check
        print("\n5. Health check...")
        health = vault.health(record['id'])
        print(f"   Status: {health['status']}")
        print(f"   Verified files: {health['verified_files']}")

        # Checkout (restore)
        print("\n6. Checking out (full restore)...")
        checkout_record = vault.checkout(record['id'], deliver_dir)
        print(f"   Delivery folder: {checkout_record['delivery']}")

        # Verify restored files
        restored_files = list(Path(checkout_record['delivery']).rglob('*.sql'))
        print(f"   Restored files: {len(restored_files)}")

        for rf in restored_files:
            orig_idx = int(rf.stem[-1])  # Extract version number
            orig_content = versions[orig_idx].read_text()
            rest_content = rf.read_text()
            match = hashlib.sha256(orig_content.encode()).hexdigest() == hashlib.sha256(rest_content.encode()).hexdigest()
            print(f"   {rf.name}: {'[OK]' if match else '[FAIL]'}")

        # Cleanup
        print("\n7. Releasing...")
        release_record = vault.release(record['id'], acknowledged=True)
        print(f"   Status: {release_record['status']}")
        print(f"   Archive removed: {release_record['managed_archive_removed']}")

        print("\n" + "="*70)
        print("CDC Vault Demo Complete!")
        print("="*70)

    finally:
        shutil.rmtree(base, ignore_errors=True)


def demo_real_world_scenario():
    """Demo with realistic data patterns."""

    print("\n" + "="*70)
    print("Real-World Scenario: Log File Deduplication")
    print("="*70)

    base = Path(tempfile.mkdtemp())
    source_dir = base / "logs"
    source_dir.mkdir()

    try:
        # Create log files with repeating patterns
        print("\nCreating log files with repeating patterns...")

        header = "=" * 80 + "\n"
        header += "COMPANY LOG SYSTEM - ALL RIGHTS RESERVED\n"
        header += "=" * 80 + "\n\n"

        log_templates = [
            "2024-01-{:02d} 08:00:00 INFO Server started on port 8080\n",
            "2024-01-{:02d} 08:15:23 INFO User login: admin from 192.168.1.100\n",
            "2024-01-{:02d} 09:30:45 WARN High memory usage: 85%\n",
            "2024-01-{:02d} 10:00:00 INFO Backup started\n",
            "2024-01-{:02d} 10:30:00 INFO Backup completed successfully\n",
        ]

        # Create 30 daily log files
        for day in range(1, 31):
            log_content = header
            for hour in range(24):
                for template in log_templates:
                    log_content += template.format(day, hour)

            log_file = source_dir / f"app_2024-01-{day:02d}.log"
            log_file.write_text(log_content)

        total_size = sum(f.stat().st_size for f in source_dir.glob('*.log'))
        print(f"   Created 30 log files: {total_size:,} bytes total")

        # Scan
        report = scan_local(source_dir)
        file_ids = [f['id'] for f in report['files']]

        # Archive
        cdc_dedup_dir = base / "cdc_archive"
        cdc_dedup_dir.mkdir()

        print("\nArchiving with CDC...")
        result = create_bundle_cdc(report, file_ids, cdc_dedup_dir)

        archive_size = (cdc_dedup_dir / result['id'] / result['archive']).stat().st_size
        print(f"   Archive size: {archive_size:,} bytes")
        print(f"   Dedup ratio: {result.get('dedup_ratio', 1.0):.2f}x")
        print(f"   Unique chunks: {result.get('unique_chunks', 'N/A')}")
        print(f"   Space saved: {(1 - archive_size/total_size)*100:.1f}%")

        # Restore
        restore_dir = base / "restored"
        restore_dir.mkdir()

        print("\nRestoring...")
        restore_result = restore_bundle_cdc(result, cdc_dedup_dir, restore_dir)

        # Find restored files (path is restore_dir/uuid/filename)
        restored_files = list(restore_dir.glob('**/*.log'))
        print(f"   Restored {len(restored_files)} files")

        # Verify
        all_ok = True
        for orig in source_dir.glob('*.log'):
            restored = [f for f in restored_files if f.name == orig.name]
            if restored:
                orig_hash = hashlib.sha256(orig.read_bytes()).hexdigest()
                rest_hash = hashlib.sha256(restored[0].read_bytes()).hexdigest()
                if orig_hash != rest_hash:
                    all_ok = False
                    print(f"   {orig.name}: [FAIL]")
            else:
                all_ok = False
                print(f"   {orig.name}: [MISSING]")

        if all_ok:
            print("   All files verified: [OK]")

        print("\n" + "="*70)
        print("Real-World Scenario Complete!")
        print("="*70)

    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    # Demo 1: Basic CDC vault workflow
    demo_cdc_vault()

    # Demo 2: Real-world log file scenario
    demo_real_world_scenario()
