"""
LMDB Local Cache for Fingerprint Storage

Provides a high-performance, persistent local cache for fingerprints
using LMDB (Lightning Memory-Mapped Database).

Features:
- mmap'd for zero-copy reads
- ACID transactions
- Configurable cache size (100GB+ per node)
- TTL support with periodic cleanup
"""

import asyncio
import lmdb
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple, Any
import os


@dataclass
class CacheEntry:
    """Cached fingerprint record"""
    fp: str
    size: int
    refcount: int
    compressed_size: int
    compression: str
    tier: str
    created_at: float
    last_accessed: float
    access_count: int

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self)).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "CacheEntry":
        return cls(**json.loads(data))


class LMDBFingerprintCache:
    """
    LMDB-based local fingerprint cache.

    Provides fast local lookups before checking the global FPDB.
    Significantly reduces network traffic for hot fingerprints.
    """

    # Database map size: 100GB default
    DEFAULT_MAP_SIZE = 100 * 1024 * 1024 * 1024
    # Sub-DBs for different data types
    DB_FINGERPRINTS = "fps"
    DB_ACCESS_TIME = "atime"  # For TTL tracking
    DB_STATS = "stats"

    def __init__(self, path: str, map_size: int = None, readonly: bool = False):
        self.path = path
        self.map_size = map_size or self.DEFAULT_MAP_SIZE
        self.readonly = readonly

        # Ensure directory exists
        os.makedirs(path, exist_ok=True)

        # Open LMDB environment
        self._env = lmdb.open(
            path,
            map_size=self.map_size,
            readonly=readonly,
            max_dbs=4,
            readahead=False,  # Disable readahead for random access
            meminit=False     # Don't initialize memory (faster startup)
        )

    def close(self):
        """Close the LMDB environment."""
        if self._env:
            self._env.close()
            self._env = None

    def _get_db(self, name: str) -> lmdb._Database:
        """Get a named sub-database."""
        return self._env.open_db(name.encode() if isinstance(name, str) else name)

    def put(self, fp: str, entry: CacheEntry) -> bool:
        """
        Store a fingerprint record.

        Args:
            fp: SHA-256 fingerprint
            entry: CacheEntry to store

        Returns:
            True if successful
        """
        if self.readonly:
            return False

        with self._env.begin(write=True) as txn:
            # Store main record (using default database)
            txn.put(fp.encode(), entry.to_bytes())

            # Update access time index for TTL
            txn.put(f"{fp}:atime".encode(), str(time.time()).encode())

        return True

    def get(self, fp: str) -> Optional[CacheEntry]:
        """
        Retrieve a fingerprint record.

        Args:
            fp: SHA-256 fingerprint

        Returns:
            CacheEntry if found, None otherwise
        """
        with self._env.begin() as txn:
            data = txn.get(fp.encode())

            if data is None:
                return None

            entry = CacheEntry.from_bytes(data)

            # Update last accessed time (lazy, don't wait)
            # In production, batch these updates

            return entry

    def delete(self, fp: str) -> bool:
        """Delete a fingerprint record."""
        if self.readonly:
            return False

        with self._env.begin(write=True) as txn:
            result = txn.delete(fp.encode())
            txn.delete(f"{fp}:atime".encode())

        return result

    def exists(self, fp: str) -> bool:
        """Check if a fingerprint exists in cache."""
        with self._env.begin() as txn:
            db = self._get_db(self.DB_FINGERPRINTS)
            return txn.get(fp.encode(), db=db) is not None

    def update_refcount(self, fp: str, delta: int) -> Optional[int]:
        """
        Atomically update refcount.

        Args:
            fp: SHA-256 fingerprint
            delta: Change in refcount (+1 or -1)

        Returns:
            New refcount, or None if not found
        """
        if self.readonly:
            return None

        with self._env.begin(write=True) as txn:
            data = txn.get(fp.encode())

            if data is None:
                return None

            entry = CacheEntry.from_bytes(data)
            entry.refcount = max(0, entry.refcount + delta)
            entry.last_accessed = time.time()
            entry.access_count += 1

            txn.put(fp.encode(), entry.to_bytes())

            return entry.refcount

    def iter_fingerprints(self, limit: int = None) -> Iterator[Tuple[str, CacheEntry]]:
        """
        Iterate over all cached fingerprints.

        Args:
            limit: Maximum number to return

        Yields:
            (fingerprint, CacheEntry) tuples
        """
        count = 0
        with self._env.begin() as txn:
            cursor = txn.cursor()

            for fp, data in cursor:
                if limit and count >= limit:
                    break
                if b':atime' in fp:
                    continue
                yield fp.decode(), CacheEntry.from_bytes(data)
                count += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "total_entries": 0,
            "total_bytes": 0,
            "total_refcount": 0,
            "avg_refcount": 0,
        }

        with self._env.begin() as txn:
            cursor = txn.cursor()

            total_refcount = 0
            total_size = 0

            for fp, data in cursor:
                if b':atime' in fp:
                    continue
                entry = CacheEntry.from_bytes(data)
                stats["total_entries"] += 1
                total_refcount += entry.refcount
                total_size += entry.size

            stats["total_bytes"] = total_size
            stats["total_refcount"] = total_refcount
            if stats["total_entries"] > 0:
                stats["avg_refcount"] = total_refcount / stats["total_entries"]

        return stats

    def cleanup_expired(self, max_age_seconds: int) -> int:
        """
        Remove entries older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds

        Returns:
            Number of entries removed
        """
        if self.readonly:
            return 0

        now = time.time()
        cutoff = now - max_age_seconds
        removed = 0

        with self._env.begin(write=True) as txn:
            cursor = txn.cursor()

            # Collect expired keys first
            expired_keys = []
            for fp, atime_data in cursor:
                if b':atime' not in fp:
                    continue
                atime = float(atime_data.decode())
                if atime < cutoff:
                    expired_keys.append(fp.replace(b':atime', b''))

            # Delete expired entries
            for fp in expired_keys:
                txn.delete(fp)
                txn.delete(fp + b':atime')
                removed += 1

        return removed

    def clear(self) -> None:
        """Clear all cached data."""
        if self.readonly:
            return

        with self._env.begin(write=True) as txn:
            txn.drop(self._env.open_db(None), delete=False)

    def get_by_refcount(self, max_refcount: int, limit: int = 1000) -> List[str]:
        """
        Get fingerprints with refcount <= max_refcount.
        Used for finding orphaned entries.

        Args:
            max_refcount: Maximum refcount threshold
            limit: Maximum number to return

        Returns:
            List of fingerprints with low refcount
        """
        results = []
        with self._env.begin() as txn:
            cursor = txn.cursor()

            for fp, data in cursor:
                if b':atime' in fp:
                    continue
                if len(results) >= limit:
                    break

                entry = CacheEntry.from_bytes(data)
                if entry.refcount <= max_refcount:
                    results.append(fp.decode())

        return results


class CacheStats:
    """Track cache hit/miss statistics."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.blom_hits = 0  # Bloom filter positive (may exist)
        self.blom_misses = 0  # Bloom filter negative (definitely not exist)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hit_rate,
            "bloom_hits": self.blom_hits,
            "bloom_misses": self.blom_misses,
        }


# Example usage
if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        cache = LMDBFingerprintCache(tmpdir, map_size=10 * 1024 * 1024)

        # Test write
        entry = CacheEntry(
            fp="abc123" * 10 + "123",  # 64 char sha256
            size=32768,
            refcount=1,
            compressed_size=8192,
            compression="zstd",
            tier="warm",
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=1
        )
        cache.put(entry.fp, entry)

        # Test read
        retrieved = cache.get(entry.fp)
        print(f"Retrieved: {retrieved.fp}, size={retrieved.size}")

        # Test stats
        print(f"Stats: {cache.get_stats()}")

        # Test not found
        missing = cache.get("notexist")
        print(f"Missing: {missing}")

        cache.close()
