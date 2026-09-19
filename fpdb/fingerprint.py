"""
Fingerprint Record Model and Database Operations

Defines the schema for fingerprint records stored in the global FPDB,
and provides operations for CRUD and deduplication logic.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import json
import hashlib


class StorageTier(Enum):
    """Storage tier classification"""
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class CompressionCodec(Enum):
    """Compression codec used"""
    NONE = "none"
    ZSTD = "zstd"
    GZIP = "gzip"
    XZ = "xz"


@dataclass
class BlobLocation:
    """Location of a blob in storage"""
    node: str       # Node ID where blob is stored
    path: str       # Path to the blob file
    tier: str       # Storage tier (hot/warm/cold)

    def to_dict(self) -> Dict:
        return {"node": self.node, "path": self.path, "tier": self.tier}

    @classmethod
    def from_dict(cls, d: Dict) -> "BlobLocation":
        return cls(node=d["node"], path=d["path"], tier=d["tier"])


@dataclass
class FingerprintRecord:
    """
    Record for a content fingerprint in the global database.

    This represents a unique chunk of data after deduplication.
    """
    fp: str                    # SHA-256 fingerprint (primary key)
    size: int                  # Original chunk size in bytes
    refcount: int = 1          # Number of files referencing this chunk
    locations: List[BlobLocation] = field(default_factory=list)
    compressed_size: int = 0   # Size after compression
    compression: str = "none"  # Codec used
    tier: str = "warm"         # Current storage tier
    created_at: str = ""       # ISO-8601 timestamp
    last_accessed: str = ""    # ISO-8601 timestamp
    access_count: int = 0      # Number of times accessed
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if not self.last_accessed:
            self.last_accessed = self.created_at

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["locations"] = [loc.to_dict() if isinstance(loc, BlobLocation) else loc for loc in self.locations]
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "FingerprintRecord":
        """Create from dictionary."""
        if "locations" in d:
            d["locations"] = [BlobLocation.from_dict(loc) if isinstance(loc, dict) else loc
                             for loc in d["locations"]]
        return cls(**d)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, s: str) -> "FingerprintRecord":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(s))

    def increment_refcount(self) -> None:
        """Increment reference count when another file references this chunk."""
        self.refcount += 1
        self.touch()

    def decrement_refcount(self) -> int:
        """Decrement reference count. Returns new refcount."""
        self.refcount = max(0, self.refcount - 1)
        self.touch()
        return self.refcount

    def touch(self) -> None:
        """Update last_accessed timestamp."""
        self.last_accessed = datetime.utcnow().isoformat() + "Z"
        self.access_count += 1

    def add_location(self, node: str, path: str, tier: str = "warm") -> None:
        """Add a storage location for this chunk."""
        self.locations.append(BlobLocation(node=node, path=path, tier=tier))

    def remove_location(self, node: str, path: str) -> bool:
        """Remove a storage location. Returns True if removed."""
        for i, loc in enumerate(self.locations):
            if loc.node == node and loc.path == path:
                self.locations.pop(i)
                return True
        return False

    def is_orphaned(self) -> bool:
        """Check if this chunk has no references and should be garbage collected."""
        return self.refcount <= 0

    def get_primary_location(self) -> Optional[BlobLocation]:
        """Get the primary (first) location."""
        return self.locations[0] if self.locations else None

    def calculate_savings(self) -> int:
        """Calculate storage savings from deduplication."""
        if not self.compressed_size:
            return 0
        return self.size - self.compressed_size


@dataclass
class ChunkInfo:
    """
    Information about a file chunk during scanning.
    Used internally during the scan->dedupe->store pipeline.
    """
    fingerprint: str      # SHA-256 of chunk content
    offset: int           # Offset in the file
    size: int             # Chunk size
    is_unique: bool = True  # Whether this chunk is new (not in FPDB)
    existing_record: Optional[FingerprintRecord] = None  # If not unique, the existing record


@dataclass
class DedupResult:
    """Result of a deduplication operation"""
    total_chunks: int
    unique_chunks: int
    duplicate_chunks: int
    original_bytes: int
    deduplicated_bytes: int
    dedup_ratio: float  # X:1 ratio
    savings_bytes: int

    def to_dict(self) -> Dict:
        return {
            "total_chunks": self.total_chunks,
            "unique_chunks": self.unique_chunks,
            "duplicate_chunks": self.duplicate_chunks,
            "original_bytes": self.original_bytes,
            "deduplicated_bytes": self.deduplicated_bytes,
            "dedup_ratio": self.dedup_ratio,
            "savings_bytes": self.savings_bytes
        }


class FingerprintCache:
    """
    Local in-memory cache for fingerprint lookups.

    Uses a simple LRU eviction policy. For production, this should
    be backed by Redis with proper TTL and invalidation.
    """

    def __init__(self, max_size: int = 100000):
        self.max_size = max_size
        self.cache: Dict[str, Optional[FingerprintRecord]] = {}  # None = definitely not found
        self.access_order: List[str] = []  # For LRU tracking

    def get(self, fingerprint: str) -> Optional[FingerprintRecord]:
        """Get a record from cache. Returns None if not found or negative hit."""
        if fingerprint in self.cache:
            # Move to end (most recently used)
            self.access_order.remove(fingerprint)
            self.access_order.append(fingerprint)
            return self.cache[fingerprint]
        return None

    def put(self, fingerprint: str, record: Optional[FingerprintRecord]) -> None:
        """Put a record into cache."""
        if fingerprint in self.cache:
            self.access_order.remove(fingerprint)
        elif len(self.cache) >= self.max_size:
            # Evict least recently used
            lru = self.access_order.pop(0)
            del self.cache[lru]

        self.cache[fingerprint] = record
        self.access_order.append(fingerprint)

    def contains(self, fingerprint: str) -> Optional[bool]:
        """
        Check if fingerprint is in cache.
        Returns True if present (may be record or None),
        None if not in cache (need to check DB).
        """
        return self.cache.get(fingerprint)

    def invalidate(self, fingerprint: str) -> None:
        """Remove a fingerprint from cache."""
        if fingerprint in self.cache:
            self.cache.pop(fingerprint)
            self.access_order.remove(fingerprint)

    def clear(self) -> None:
        """Clear the entire cache."""
        self.cache.clear()
        self.access_order.clear()


def compute_fingerprint(data: bytes) -> str:
    """Compute SHA-256 fingerprint of data."""
    return hashlib.sha256(data).hexdigest()


def verify_fingerprint(data: bytes, fingerprint: str) -> bool:
    """Verify that data matches the given fingerprint."""
    return compute_fingerprint(data) == fingerprint


# Schema for ScyllaDB/Cassandra
FPDB_SCHEMA = """
CREATE TABLE IF NOT EXISTS fingerprints (
    fp text PRIMARY KEY,           -- SHA-256 fingerprint
    size int,                      -- Original chunk size
    refcount int,                  -- Reference count
    locations list<text>,          -- JSON array of BlobLocation
    compressed_size int,           -- Size after compression
    compression text,              -- Codec used
    tier text,                     -- Current storage tier
    created_at timestamp,          -- Creation timestamp
    last_accessed timestamp,       -- Last access timestamp
    access_count int,              -- Access counter
    metadata map<text, text        -- Additional metadata
) WITH compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'window_unit': 'DAYS',
    'window_size': '1'
};

CREATE INDEX IF NOT EXISTS idx_fp_refcount ON fingerprints(refcount);
CREATE INDEX IF NOT EXISTS idx_fp_tier ON fingerprints(tier);
CREATE INDEX IF NOT EXISTS idx_fp_created_at ON fingerprints(created_at);
"""

# Example queries for the fingerprint table
FPDB_QUERIES = {
    "insert": """
        INSERT INTO fingerprints (fp, size, refcount, locations, compressed_size,
                                  compression, tier, created_at, last_accessed,
                                  access_count, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "select": """
        SELECT * FROM fingerprints WHERE fp = ?
    """,
    "increment_refcount": """
        UPDATE fingerprints SET refcount = refcount + 1,
                                last_accessed = ?,
                                access_count = access_count + 1
        WHERE fp = ?
    """,
    "delete_location": """
        UPDATE fingerprints SET locations = locations - ?
        WHERE fp = ?
    """,
    "select_orphaned": """
        SELECT * FROM fingerprints WHERE refcount <= 0
    """,
    "select_by_tier": """
        SELECT * FROM fingerprints WHERE tier = ?
    """
}
