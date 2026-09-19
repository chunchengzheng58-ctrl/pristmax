"""
CDC vs File-Level Deduplication Comparison Demo

Tests with MULTIPLE similar files to show CDC's advantage:
1. Original file-level deduplication
2. New CDC chunk-level deduplication

CDC shines when files have similar content (versions, backups, etc.)
"""

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from storage_core import digest_stream, scan_local
from deep_archive import create_bundle as create_file_dedup, restore_bundle as restore_file_dedup
from deep_archive_cdc import create_bundle_cdc, restore_bundle_cdc


def test_with_multiple_similar_files():
    """Test with multiple similar files to demonstrate CDC advantage."""

    print("="*70)
    print("CDC vs File-Level Deduplication - Multiple Similar Files Test")
    print("="*70)

    # Create temp directories
    base = Path(tempfile.mkdtemp())
    source_dir = base / "source"
    file_dedup_dir = base / "file_dedup"
    cdc_dedup_dir = base / "cdc_dedup"
    file_restore_dir = base / "file_restore"
    cdc_restore_dir = base / "cdc_dedup_restore"

    for d in [source_dir, file_dedup_dir, cdc_dedup_dir, file_restore_dir, cdc_restore_dir]:
        d.mkdir(parents=True)

    # Create test files with similar content (simulating versioned data)
    print("\nCreating test files with similar content...")

    base_content = b"This is a common header for all files. " * 1000
    base_content += b"Unique content for file 1. " * 500
    base_content += b"=" * 1000  # padding

    files_created = []
    for i in range(5):
        # Each file shares 80% common content, 20% unique
        if i == 0:
            content = base_content
        else:
            # Modify only 20% of the content
            content = base_content[:int(len(base_content)*0.8)]
            content += f"\n\n=== UNIQUE CONTENT FOR FILE {i} ===\n".encode() * 500
            content += b"=" * 500

        file_path = source_dir / f"document_v{i}.txt"
        file_path.write_bytes(content)
        files_created.append(file_path)
        print(f"  Created: {file_path.name} ({len(content):,} bytes)")

    # Get original info
    original_size = sum(f.stat().st_size for f in files_created)
    print(f"\n  Total original size: {original_size:,} bytes")

    # Create scan report
    print("\nScanning source files...")
    report = scan_local(source_dir)
    file_ids = [f['id'] for f in report['files']]
    print(f"  Found {len(file_ids)} files")

    # Test 1: File-level deduplication
    print("\n" + "="*70)
    print("Test 1: File-Level Deduplication (Original)")
    print("="*70)

    result1 = create_file_dedup(
        report,
        file_ids,
        file_dedup_dir,
        progress=lambda x: print(f"  {x.get('current', '')}", end='\r')
    )

    archive1_path = file_dedup_dir / result1['id'] / result1['archive']
    archive1_size = archive1_path.stat().st_size if archive1_path.exists() else 0

    print(f"\n  Archive size: {archive1_size:,} bytes")
    print(f"  Compression: {result1.get('codec', 'N/A').upper()}")
    dedup1_ratio = result1.get('original_bytes', original_size) / archive1_size if archive1_size > 0 else 1.0
    print(f"  Dedup ratio: {dedup1_ratio:.2f}x")
    print(f"  Space saved: {(1 - archive1_size/original_size)*100:.1f}%" if archive1_size > 0 else "  N/A")

    # Test 2: CDC chunk-level deduplication
    print("\n" + "="*70)
    print("Test 2: CDC Chunk-Level Deduplication (Optimized)")
    print("="*70)

    result2 = create_bundle_cdc(
        report,
        file_ids,
        cdc_dedup_dir,
        progress=lambda x: print(f"  {x.get('current', '')}", end='\r')
    )

    archive2_path = cdc_dedup_dir / result2['id'] / result2['archive']
    archive2_size = archive2_path.stat().st_size if archive2_path.exists() else 0

    print(f"\n  Archive size: {archive2_size:,} bytes")
    print(f"  Compression: {result2.get('codec', 'N/A').upper()}")
    dedup2_ratio = result2.get('dedup_ratio', 1.0)
    print(f"  Dedup ratio: {dedup2_ratio:.2f}x")
    print(f"  Unique chunks: {result2.get('unique_chunks', 'N/A')}")
    print(f"  Total chunks: {result2.get('total_chunks', 'N/A')}")
    print(f"  Space saved: {(1 - archive2_size/original_size)*100:.1f}%" if archive2_size > 0 else "  N/A")

    # Restore and verify
    print("\n" + "="*70)
    print("Restore Verification")
    print("="*70)

    # Restore file-level
    try:
        result_r1 = restore_file_dedup(result1, file_dedup_dir, file_restore_dir)
        restored_files = list(file_restore_dir.glob('*/*/document_v*.txt'))
        print(f"\n  File-Level Restore: {len(restored_files)} files restored")

        # Verify first file
        if restored_files:
            first_file = restored_files[0]
            restored_md5 = hashlib.md5(first_file.read_bytes()).hexdigest()
            original_md5 = hashlib.md5(files_created[0].read_bytes()).hexdigest()
            print(f"    First file MD5 match: {'[OK]' if restored_md5 == original_md5 else '[FAIL]'}")
    except Exception as e:
        print(f"  File-Level Restore error: {e}")

    # Restore CDC
    try:
        result_r2 = restore_bundle_cdc(result2, cdc_dedup_dir, cdc_restore_dir)
        restored_files = list(cdc_restore_dir.glob('*/*/document_v*.txt'))
        print(f"\n  CDC Restore: {len(restored_files)} files restored")

        # Verify first file
        if restored_files:
            first_file = restored_files[0]
            restored_md5 = hashlib.md5(first_file.read_bytes()).hexdigest()
            original_md5 = hashlib.md5(files_created[0].read_bytes()).hexdigest()
            print(f"    First file MD5 match: {'[OK]' if restored_md5 == original_md5 else '[FAIL]'}")
    except Exception as e:
        print(f"  CDC Restore error: {e}")

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"{'Method':<30} {'Archive Size':<15} {'Dedup Ratio':<12} {'Space Saved'}")
    print("-"*70)
    if archive1_size > 0:
        print(f"{'File-Level Dedup':<30} {archive1_size:>12,} B    {dedup1_ratio:>8.2f}x    {(1 - archive1_size/original_size)*100:>8.1f}%")
    if archive2_size > 0:
        print(f"{'CDC Chunk-Level Dedup':<30} {archive2_size:>12,} B    {dedup2_ratio:>8.2f}x    {(1 - archive2_size/original_size)*100:>8.1f}%")
    print("-"*70)

    if archive1_size > 0 and archive2_size > 0:
        if archive2_size < archive1_size:
            improvement = (archive1_size - archive2_size) / archive1_size * 100
            print(f"\n  CDC is {improvement:.1f}% MORE efficient than file-level dedup")
        else:
            regression = (archive2_size - archive1_size) / archive1_size * 100
            print(f"\n  Note: CDC is {regression:.1f}% less efficient for this case")
            print(f"  (CDC shines with larger files and more internal repetition)")

    # Cleanup
    shutil.rmtree(base, ignore_errors=True)

    print("\n  Test files cleaned up.")


def test_single_jpeg():
    """Test with single JPEG file from Desktop."""

    source = Path('C:/Users/zcc36/Desktop/123/0.jpg')

    if not source.exists():
        print(f"Error: {source} not found")
        return

    original_size = source.stat().st_size
    original_md5 = hashlib.md5(source.read_bytes()).hexdigest()

    print("\n" + "="*70)
    print("Single JPEG File Test (Desktop/123/0.jpg)")
    print("="*70)
    print(f"  Original size: {original_size:,} bytes")
    print(f"  Note: CDC benefit shows when multiple similar files exist")
    print(f"  For a single file, CDC and file-level dedup are similar")

    # Create temp directories
    base = Path(tempfile.mkdtemp())
    demo_dir = base / "demo_source"
    file_dedup_dir = base / "file_dedup"
    cdc_dedup_dir = base / "cdc_dedup"

    for d in [demo_dir, file_dedup_dir, cdc_dedup_dir]:
        d.mkdir()

    # Copy source file
    shutil.copy2(source, demo_dir / "test.jpg")

    # Scan
    report = scan_local(demo_dir)
    file_id = report['files'][0]['id']

    # File-level
    result1 = create_file_dedup(report, [file_id], file_dedup_dir)
    archive1_size = (file_dedup_dir / result1['id'] / result1['archive']).stat().st_size

    # CDC
    result2 = create_bundle_cdc(report, [file_id], cdc_dedup_dir)
    archive2_size = (cdc_dedup_dir / result2['id'] / result2['archive']).stat().st_size

    print(f"\n  File-Level: {archive1_size:,} bytes (saved {(1-archive1_size/original_size)*100:.1f}%)")
    print(f"  CDC:        {archive2_size:,} bytes (saved {(1-archive2_size/original_size)*100:.1f}%)")

    shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    # Run multi-file test first (shows CDC advantage)
    test_with_multiple_similar_files()

    # Then run single file test
    test_single_jpeg()
