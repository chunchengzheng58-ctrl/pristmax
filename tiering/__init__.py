"""Storage Atlas - PB-Scale Storage Optimization System"""

__version__ = "0.5.0"
__pb_scale__ = True

# Core modules
from tiering.storage_backend import (
    StorageBackend,
    StorageTier,
    CompressionCodec,
    TierManager,
    create_backend,
    NVMeBackend,
    S3Backend,
)

from tiering.policy import (
    TierPolicyEngine,
    TierOptimizer,
    ClassificationContext,
    ClassificationResult,
    PolicyPriority,
)

from tiering.migration import (
    MigrationScheduler,
    MigrationTask,
    MigrationBatch,
    MigrationStatus,
    TierMigrationManager,
)

from tiering.monitor import (
    TierMonitor,
    TierDashboard,
    TierStats,
    GlobalTierStats,
    CostStats,
    Alert,
)

from fpdb.sharding import (
    ConsistentHashRing,
    ShardRouter,
    ShardInfo,
)

from fpdb.fingerprint import (
    FingerprintRecord,
    BlobLocation,
    ChunkInfo,
    DedupResult,
    compute_fingerprint,
    verify_fingerprint,
)

from fpdb.client import (
    FPDBClient,
    FPDBClientWithCache,
    BloomFilterCache,
    FPDBConsistency,
)

from cdc.chunker import (
    RabinFingerprint,
    Chunk,
    DedupChunk,
    DeduplicatingChunker,
    rabin_chunks,
)

from coordinator.node import (
    NodeInfo,
    NodeState,
    NodeRole,
    TaskInfo,
    NodeRegistry,
    TaskScheduler,
    LeaderElection,
)

from scannode.worker import (
    ScanOptions,
    FileRecord,
    ScanResult,
    LocalScanner,
    ScanNode,
)

from dedupe.pipeline import (
    DedupPipeline,
    StreamingDedupPipeline,
    DedupStrategy,
    FileDedupResult,
    DedupStats,
    ChunkRef,
)

from dedupe.lmdb_cache import (
    LMDBFingerprintCache,
    CacheEntry,
)

from dedupe.bloom_sync import (
    BloomFilterManager,
    SimpleBloomFilter,
)

from resilience.checkpoint import (
    CheckpointStatus,
    Checkpoint,
    CheckpointManager,
    TaskRecoveryManager,
)

from resilience.distlock import (
    LockStatus,
    DistributedLock,
    ReadWriteLock,
    LeaderElection as DistLeaderElection,
    ResourceAllocator,
)

from resilience.metrics import (
    MetricsRegistry,
    StorageAtlasMetrics,
    MetricsCollector,
)

from resilience.health import (
    HealthStatus,
    HealthCheck,
    NodeHealth,
    HealthCheckManager,
    ClusterHealthMonitor,
)

__all__ = [
    # Version
    "__version__",
    "__pb_scale__",

    # Storage Tiering
    "StorageBackend",
    "StorageTier",
    "CompressionCodec",
    "TierManager",
    "create_backend",
    "NVMeBackend",
    "S3Backend",
    "TierPolicyEngine",
    "TierOptimizer",
    "ClassificationContext",
    "ClassificationResult",
    "PolicyPriority",
    "MigrationScheduler",
    "MigrationTask",
    "MigrationBatch",
    "MigrationStatus",
    "TierMigrationManager",
    "TierMonitor",
    "TierDashboard",
    "TierStats",
    "GlobalTierStats",
    "CostStats",
    "Alert",

    # FPDB
    "ConsistentHashRing",
    "ShardRouter",
    "ShardInfo",
    "FingerprintRecord",
    "BlobLocation",
    "ChunkInfo",
    "DedupResult",
    "compute_fingerprint",
    "verify_fingerprint",
    "FPDBClient",
    "FPDBClientWithCache",
    "BloomFilterCache",
    "FPDBConsistency",

    # CDC
    "RabinFingerprint",
    "Chunk",
    "DedupChunk",
    "DeduplicatingChunker",
    "rabin_chunks",

    # Coordination
    "NodeInfo",
    "NodeState",
    "NodeRole",
    "TaskInfo",
    "NodeRegistry",
    "TaskScheduler",

    # Scan Node
    "ScanOptions",
    "FileRecord",
    "ScanResult",
    "LocalScanner",
    "ScanNode",

    # Deduplication
    "DedupPipeline",
    "StreamingDedupPipeline",
    "DedupStrategy",
    "FileDedupResult",
    "DedupStats",
    "ChunkRef",
    "LMDBFingerprintCache",
    "CacheEntry",
    "BloomFilterManager",
    "SimpleBloomFilter",

    # Resilience
    "CheckpointStatus",
    "Checkpoint",
    "CheckpointManager",
    "TaskRecoveryManager",
    "LockStatus",
    "DistributedLock",
    "ReadWriteLock",
    "DistLeaderElection",
    "ResourceAllocator",
    "MetricsRegistry",
    "StorageAtlasMetrics",
    "MetricsCollector",
    "HealthStatus",
    "HealthCheck",
    "NodeHealth",
    "HealthCheckManager",
    "ClusterHealthMonitor",
]
