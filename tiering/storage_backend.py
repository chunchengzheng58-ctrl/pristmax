"""
Storage Backend Abstraction Layer

Provides a unified interface for multiple storage backends:
- NVMe/SSD (local hot storage)
- HDD arrays (warm storage)
- S3-compatible object storage (cold storage)
- HDFS (distributed filesystem)
- Ceph RGW (enterprise storage)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Dict, List, Optional, Any
import asyncio
import hashlib


class StorageTier(Enum):
    """Storage tier classification"""
    HOT = "hot"      # NVMe SSD, fast access, no compression
    WARM = "warm"    # HDD array, medium latency, Zstd compression
    COLD = "cold"    # S3 Glacier, high latency, XZ compression


class CompressionCodec(Enum):
    """Compression codec per tier"""
    NONE = "none"
    ZSTD = "zstd"    # Fast, good ratio, balanced
    GZIP = "gzip"    # Compatible, moderate
    XZ = "xz"        # Best ratio, slow


@dataclass
class WriteResult:
    """Result of a write operation"""
    key: str
    size: int
    compressed_size: int
    checksum: str  # SHA-256 of the stored data
    backend: str
    tier: StorageTier


@dataclass
class BlobHandle:
    """Handle to a stored blob"""
    key: str
    backend: str
    tier: StorageTier
    size: int
    checksum: str


@dataclass
class TierPolicy:
    """Policy for automatic tier classification"""
    tier: StorageTier
    max_age_days: Optional[int] = None
    max_access_count: Optional[int] = None
    compression: CompressionCodec = CompressionCodec.NONE
    replication_factor: int = 1
    backend_type: str = "local"


# Default tier policies
DEFAULT_POLICIES = {
    StorageTier.HOT: TierPolicy(
        tier=StorageTier.HOT,
        max_age_days=30,
        max_access_count=1000,
        compression=CompressionCodec.NONE,
        replication_factor=3,
        backend_type="nvme"
    ),
    StorageTier.WARM: TierPolicy(
        tier=StorageTier.WARM,
        max_age_days=180,
        max_access_count=100,
        compression=CompressionCodec.ZSTD,
        replication_factor=2,
        backend_type="hdd"
    ),
    StorageTier.COLD: TierPolicy(
        tier=StorageTier.COLD,
        max_age_days=None,  # No limit
        max_access_count=10,
        compression=CompressionCodec.XZ,
        replication_factor=3,
        backend_type="s3"
    ),
}


class StorageBackend(ABC):
    """
    Abstract base class for storage backends.

    All implementations must be async-compatible for concurrent operations.
    """

    def __init__(self, backend_type: str, tier: StorageTier, config: Dict[str, Any]):
        self.backend_type = backend_type
        self.tier = tier
        self.config = config
        self.policy = DEFAULT_POLICIES.get(tier, TierPolicy(tier=tier))

    @abstractmethod
    async def write(self, key: str, data: bytes, metadata: Optional[Dict] = None) -> WriteResult:
        """
        Write data to storage.

        Args:
            key: Unique key for the blob (typically SHA-256 fingerprint)
            data: Raw bytes to store
            metadata: Optional metadata dict

        Returns:
            WriteResult with storage details
        """
        pass

    @abstractmethod
    async def read(self, key: str) -> bytes:
        """
        Read data from storage.

        Args:
            key: Blob key

        Returns:
            Raw bytes

        Raises:
            KeyError: If blob not found
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Delete a blob from storage.

        Args:
            key: Blob key to delete
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a blob exists."""
        pass

    @abstractmethod
    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[str]:
        """List keys with optional prefix filter."""
        pass

    async def get_metadata(self, key: str) -> Optional[Dict]:
        """Get metadata for a blob. Override if backend supports metadata."""
        return None

    def compress_data(self, data: bytes) -> tuple[bytes, CompressionCodec]:
        """Compress data according to tier policy."""
        if self.policy.compression == CompressionCodec.NONE:
            return data, CompressionCodec.NONE
        elif self.policy.compression == CompressionCodec.ZSTD:
            import zstandard as zstd
            cctx = zstd.ZstdCompressor(level=6)
            return cctx.compress(data), CompressionCodec.ZSTD
        elif self.policy.compression == CompressionCodec.GZIP:
            import gzip
            return gzip.compress(data, level=6), CompressionCodec.GZIP
        elif self.policy.compression == CompressionCodec.XZ:
            import lzma
            return lzma.compress(data, preset=9), CompressionCodec.XZ
        return data, CompressionCodec.NONE

    def checksum_data(self, data: bytes) -> str:
        """Compute SHA-256 checksum of data."""
        return hashlib.sha256(data).hexdigest()


class NVMeBackend(StorageBackend):
    """Local NVMe/SSD storage for hot tier."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("nvme", StorageTier.HOT, config)
        self.base_path = config.get("base_path", "/data/hot")
        import os
        os.makedirs(self.base_path, exist_ok=True)

    async def write(self, key: str, data: bytes, metadata: Optional[Dict] = None) -> WriteResult:
        import os
        path = os.path.join(self.base_path, key[:2], key[2:4], key)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        compressed, codec = self.compress_data(data)
        checksum = self.checksum_data(compressed)

        with open(path, 'wb') as f:
            f.write(compressed)

        return WriteResult(
            key=key,
            size=len(data),
            compressed_size=len(compressed),
            checksum=checksum,
            backend=self.backend_type,
            tier=self.tier
        )

    async def read(self, key: str) -> bytes:
        import os
        path = os.path.join(self.base_path, key[:2], key[2:4], key)
        with open(path, 'rb') as f:
            return f.read()

    async def delete(self, key: str) -> None:
        import os
        path = os.path.join(self.base_path, key[:2], key[2:4], key)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    async def exists(self, key: str) -> bool:
        import os
        path = os.path.join(self.base_path, key[:2], key[2:4], key)
        return os.path.exists(path)

    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[str]:
        import os
        keys = []
        for root, dirs, files in os.walk(self.base_path):
            for f in files:
                if f.startswith(prefix):
                    keys.append(f)
                if len(keys) >= limit:
                    return keys
        return keys


class S3Backend(StorageBackend):
    """S3-compatible object storage for cold tier."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("s3", StorageTier.COLD, config)
        self.bucket = config.get("bucket", "storage-atlas")
        self.prefix = config.get("prefix", "blobs/")
        self.endpoint = config.get("endpoint")  # Optional custom endpoint

        # Lazy import boto3
        import boto3
        self.s3 = boto3.client('s3',
            endpoint_url=self.endpoint,
            region_name=config.get("region", "us-east-1")
        )

    async def write(self, key: str, data: bytes, metadata: Optional[Dict] = None) -> WriteResult:
        compressed, codec = self.compress_data(data)
        checksum = self.checksum_data(compressed)

        s3_key = f"{self.prefix}{key[:2]}/{key[2:4]}/{key}"

        self.s3.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=compressed,
            Metadata=metadata or {},
            StorageClass='GLACIER' if self.tier == StorageTier.COLD else 'STANDARD'
        )

        return WriteResult(
            key=key,
            size=len(data),
            compressed_size=len(compressed),
            checksum=checksum,
            backend=self.backend_type,
            tier=self.tier
        )

    async def read(self, key: str) -> bytes:
        s3_key = f"{self.prefix}{key[:2]}/{key[2:4]}/{key}"
        response = self.s3.get_object(Bucket=self.bucket, Key=s3_key)
        return response['Body'].read()

    async def delete(self, key: str) -> None:
        s3_key = f"{self.prefix}{key[:2]}/{key[2:4]}/{key}"
        self.s3.delete_object(Bucket=self.bucket, Key=s3_key)

    async def exists(self, key: str) -> bool:
        s3_key = f"{self.prefix}{key[:2]}/{key[2:4]}/{key}"
        try:
            self.s3.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except:
            return False

    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[str]:
        s3_prefix = f"{self.prefix}{prefix}"
        response = self.s3.list_objects_v2(
            Bucket=self.bucket,
            Prefix=s3_prefix,
            MaxKeys=limit
        )
        keys = []
        for obj in response.get('Contents', []):
            key = obj['Key'][len(self.prefix):]  # Strip prefix
            keys.append(key)
        return keys


class TierManager:
    """
    Manages data across storage tiers with automatic classification and migration.
    """

    def __init__(self):
        self.backends: Dict[StorageTier, StorageBackend] = {}
        self.policies = DEFAULT_POLICIES.copy()

    def register_backend(self, tier: StorageTier, backend: StorageBackend):
        """Register a storage backend for a tier."""
        self.backends[tier] = backend

    def get_backend(self, tier: StorageTier) -> StorageBackend:
        """Get the backend for a specific tier."""
        return self.backends.get(tier)

    def classify(self, fingerprint: str, size: int, access_count: int,
                 age_days: int, refcount: int) -> StorageTier:
        """
        Classify a chunk into the appropriate tier based on policy.

        Args:
            fingerprint: SHA-256 fingerprint
            size: Chunk size in bytes
            access_count: Number of times accessed
            age_days: Age in days since creation
            refcount: Reference count (higher = more important)

        Returns:
            Recommended StorageTier
        """
        hot_policy = self.policies[StorageTier.HOT]
        warm_policy = self.policies[StorageTier.WARM]

        # Check hot tier conditions
        if hot_policy.max_age_days and age_days < hot_policy.max_age_days:
            if hot_policy.max_access_count is None or access_count < hot_policy.max_access_count:
                return StorageTier.HOT

        # Check warm tier conditions
        if warm_policy.max_age_days and age_days < warm_policy.max_age_days:
            return StorageTier.WARM

        # Default to cold
        return StorageTier.COLD

    async def store(self, fingerprint: str, data: bytes,
                   metadata: Optional[Dict] = None) -> WriteResult:
        """
        Store a blob in the appropriate tier based on classification.
        """
        # Classify based on metadata if available
        access_count = metadata.get("access_count", 0) if metadata else 0
        age_days = metadata.get("age_days", 0) if metadata else 0

        tier = self.classify(fingerprint, len(data), access_count, age_days, refcount=1)
        backend = self.get_backend(tier)

        if backend is None:
            raise ValueError(f"No backend registered for tier {tier}")

        return await backend.write(fingerprint, data, metadata)

    async def retrieve(self, fingerprint: str, min_tier: StorageTier = StorageTier.COLD) -> bytes:
        """
        Retrieve a blob, trying tiers from hot to cold as needed.
        """
        for tier in [StorageTier.HOT, StorageTier.WARM, StorageTier.COLD]:
            if tier.value < min_tier.value:
                continue
            backend = self.get_backend(tier)
            if backend and await backend.exists(fingerprint):
                return await backend.read(fingerprint)

        raise KeyError(f"Blob {fingerprint} not found in any tier")

    async def migrate(self, fingerprint: str, from_tier: StorageTier,
                     to_tier: StorageTier) -> WriteResult:
        """
        Migrate a blob from one tier to another.
        """
        source = self.get_backend(from_tier)
        target = self.get_backend(to_tier)

        if source is None or target is None:
            raise ValueError(f"Invalid tier migration: {from_tier} -> {to_tier}")

        # Read from source
        data = await source.read(fingerprint)

        # Write to target
        result = await target.write(fingerprint, data)

        # Delete from source if successful
        await source.delete(fingerprint)

        return result


# Backend factory
def create_backend(backend_type: str, config: Dict[str, Any]) -> StorageBackend:
    """Factory function to create storage backends."""
    backend_map = {
        "nvme": NVMeBackend,
        "s3": S3Backend,
        # Add more backends as needed
        # "hdfs": HDFSBackend,
        # "ceph": CephBackend,
    }

    backend_class = backend_map.get(backend_type)
    if backend_class is None:
        raise ValueError(f"Unknown backend type: {backend_type}")

    return backend_class(config)
