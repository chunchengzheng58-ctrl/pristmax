# -*- coding: utf-8 -*-
"""
Phase 4 - Storage Backend Integration Demo

Demonstrates:
1. Local filesystem storage
2. S3-compatible storage (mock mode)
3. Storage backend abstraction
"""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from semantic_reduction.storage.filesystem import FileSystemBackend
from semantic_reduction.storage.s3_backend import S3Backend, OSSBackend, COSBackend


def demo_filesystem_backend():
    """Demo: Local filesystem storage"""
    print("\n" + "="*70)
    print("Phase 4 - FileSystem Storage Demo")
    print("="*70)

    # Initialize storage
    storage = FileSystemBackend("./data/storage")

    print("\n[1] Storing test video...")
    test_video = "./data/test_video.mp4"
    if not Path(test_video).exists():
        print("  Creating test file...")
        Path(test_video).write_bytes(b"test video content" * 1000)

    file_info = storage.store(test_video, "videos/test_video.mp4")
    print(f"  Stored: {file_info.file_id}")
    print(f"  Path: {file_info.path}")
    print(f"  Size: {file_info.size:,} bytes")
    print(f"  Checksum: {file_info.checksum[:16]}...")

    print("\n[2] Storing test image...")
    test_image = "./data/test_people.jpg"
    if Path(test_image).exists():
        img_info = storage.store(test_image, "images/test_people.jpg")
        print(f"  Stored: {img_info.file_id}")
        print(f"  Path: {img_info.path}")
        print(f"  Size: {img_info.size:,} bytes")

    print("\n[3] Listing stored files...")
    files = storage.list_files()
    print(f"  Total files: {len(files)}")
    for f in files:
        print(f"    - {f.path} ({f.size:,} bytes)")

    print("\n[4] Storage usage...")
    usage = storage.get_usage()
    print(f"  Total bytes: {usage['total_bytes']:,}")
    print(f"  Total files: {usage['total_files']}")
    print(f"  Base path: {usage['base_path']}")

    print("\n[5] Retrieving file...")
    retrieved = storage.retrieve("videos/test_video.mp4", "./data/retrieved_video.mp4")
    print(f"  Retrieved to: {retrieved}")
    print(f"  File exists: {Path(retrieved).exists()}")

    print("\n[6] Verifying checksum...")
    is_valid = storage.verify_file("videos/test_video.mp4", file_info.checksum)
    print(f"  Checksum valid: {is_valid}")

    print("\n[7] Statistics...")
    stats = storage.get_stats()
    print(f"  Files stored: {stats['files_stored']}")
    print(f"  Bytes stored: {stats['bytes_stored']:,}")
    print(f"  Files deleted: {stats['files_deleted']}")
    print(f"  Errors: {stats['errors']}")

    print("\n[8] Deleting file...")
    deleted = storage.delete("videos/test_video.mp4")
    print(f"  Deleted: {deleted}")
    print(f"  Remaining files: {len(storage.list_files())}")


def demo_s3_backend_mock():
    """Demo: S3 backend in mock mode (no real credentials)"""
    print("\n" + "="*70)
    print("Phase 4 - S3 Storage Demo (Mock Mode)")
    print("="*70)

    print("""
[INFO] Real S3 operations require valid credentials:
       AWS S3:     pip install boto3
       MinIO:      pip install minio
       Alibaba OSS: pip install oss2
       Tencent COS: pip install qcloud-cos-sdk-v5

[INFO] Running in mock mode - simulates S3 operations locally
""")

    # Initialize S3 backend with mock credentials
    s3 = S3Backend(
        endpoint="https://s3.example.com",
        access_key="mock_access_key",
        secret_key="mock_secret_key",
        bucket="test-bucket",
        region="us-east-1",
        provider="aws"
    )

    print("\n[1] Initializing S3 backend...")
    initialized = s3.initialize()
    print(f"  Initialized: {initialized}")
    print(f"  Provider: {s3.provider}")
    print(f"  Bucket: {s3.bucket}")
    print(f"  Mock mode: {getattr(s3, '_mock_mode', False)}")

    print("\n[2] Storing file (mock)...")
    test_file = "./data/test_video.mp4"
    if not Path(test_file).exists():
        Path(test_file).write_bytes(b"test data" * 100)

    try:
        file_info = s3.store(test_file, "videos/test.mp4")
        print(f"  Stored: {file_info.file_id}")
        print(f"  Path: {file_info.path}")
        print(f"  Size: {file_info.size:,} bytes")
        print(f"  Storage class: {file_info.storage_class}")
    except Exception as e:
        print(f"  Error (expected in mock): {e}")

    print("\n[3] Listing files (mock)...")
    files = s3.list_files("videos/")
    print(f"  Files found: {len(files)}")

    print("\n[4] Storage usage (mock)...")
    usage = s3.get_usage()
    print(f"  Total bytes: {usage['total_bytes']}")
    print(f"  Total files: {usage['total_files']}")

    print("\n[5] Statistics...")
    stats = s3.get_stats()
    print(f"  Files stored: {stats['files_stored']}")
    print(f"  Bytes stored: {stats['bytes_stored']:,}")


def demo_oss_backend():
    """Demo: Alibaba Cloud OSS backend"""
    print("\n" + "="*70)
    print("Phase 4 - Alibaba Cloud OSS Demo (Mock)")
    print("="*70)

    print("""
[INFO] Alibaba Cloud OSS requires:
       pip install oss2

[INFO] Configuration:
       - endpoint: oss-cn-hangzhou.aliyuncs.com
       - access_key: Your AccessKey ID
       - secret_key: Your AccessKey Secret
       - bucket: Your bucket name
""")

    oss = OSSBackend(
        endpoint="oss-cn-hangzhou.aliyuncs.com",
        access_key="mock_access_key",
        secret_key="mock_secret_key",
        bucket="my-bucket",
        region="cn-hangzhou"
    )

    print("\n[1] Initializing OSS backend...")
    initialized = oss.initialize()
    print(f"  Initialized: {initialized}")
    print(f"  Provider: {oss.provider}")
    print(f"  Region: {oss.region}")


def demo_cos_backend():
    """Demo: Tencent Cloud COS backend"""
    print("\n" + "="*70)
    print("Phase 4 - Tencent Cloud COS Demo (Mock)")
    print("="*70)

    print("""
[INFO] Tencent Cloud COS requires:
       pip install qcloud-cos-sdk-v5

[INFO] Configuration:
       - endpoint: cos.ap-guangzhou.myqcloud.com
       - access_key: Your SecretId
       - secret_key: Your SecretKey
       - bucket: Your bucket name (e.g., mybucket-1234567890)
""")

    cos = COSBackend(
        endpoint="cos.ap-guangzhou.myqcloud.com",
        access_key="mock_access_key",
        secret_key="mock_secret_key",
        bucket="my-bucket-1234567890",
        region="ap-guangzhou"
    )

    print("\n[1] Initializing COS backend...")
    initialized = cos.initialize()
    print(f"  Initialized: {initialized}")
    print(f"  Provider: {cos.provider}")
    print(f"  Region: {cos.region}")


def demo_storage_comparison():
    """Demo: Compare different storage backends"""
    print("\n" + "="*70)
    print("Phase 4 - Storage Backend Comparison")
    print("="*70)

    backends = [
        ("FileSystem", FileSystemBackend("./data/storage")),
        ("S3 (Mock)", S3Backend("https://s3.amazonaws.com", "key", "secret", "bucket", provider="aws")),
        ("OSS (Mock)", OSSBackend("oss-cn-hangzhou.aliyuncs.com", "key", "secret", "bucket")),
        ("COS (Mock)", COSBackend("cos.ap-guangzhou.myqcloud.com", "key", "secret", "bucket")),
    ]

    print("\n[1] Backend Comparison:")
    print("-" * 70)
    print(f"{'Backend':<20} {'Provider':<15} {'Mock':<10} {'Initialized'}")
    print("-" * 70)

    for name, backend in backends:
        if hasattr(backend, 'initialize'):
            backend.initialize()
        is_mock = getattr(backend, '_mock_mode', False)
        initialized = getattr(backend, '_initialized', True)
        provider = getattr(backend, 'provider', 'filesystem')
        print(f"{name:<20} {provider:<15} {str(is_mock):<10} {initialized}")

    print("\n[2] Feature Matrix:")
    print("-" * 70)
    print(f"{'Feature':<30} {'FileSystem':<15} {'S3/OSS/COS'}")
    print("-" * 70)
    print(f"{'Local storage':<30} {'Yes':<15} {'No'}")
    print(f"{'Cloud storage':<30} {'No':<15} {'Yes'}")
    print(f"{'Checksums':<30} {'Yes':<15} {'Yes'}")
    print(f"{'Multipart upload':<30} {'No':<15} {'Yes'}")
    print(f"{'Storage classes':<30} {'No':<15} {'Yes'}")
    print(f"{'Lifecycle policies':<30} {'No':<15} {'Yes'}")


def main():
    print("\n" + "#"*70)
    print("# Phase 4 - Storage Backend Integration Demo")
    print("#"*70)
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*70)

    try:
        demo_filesystem_backend()
        demo_s3_backend_mock()
        demo_oss_backend()
        demo_cos_backend()
        demo_storage_comparison()

        print("\n" + "#"*70)
        print("# Phase 4 Demo Complete")
        print("#"*70)
        print("""
Storage Backend Features:
- FileSystem: Local storage with checksums
- S3: AWS S3 and compatible
- OSS: Alibaba Cloud Object Storage
- COS: Tencent Cloud Object Storage

Storage Operations:
- store(): Upload file with optional checksums
- retrieve(): Download file
- delete(): Remove file
- list_files(): List files with prefix filter
- get_usage(): Storage statistics
- verify_file(): Checksum verification

Next Steps:
1. Configure real cloud credentials
2. Set up storage lifecycle policies
3. Enable multipart upload for large files
4. Deploy with Docker
""")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
