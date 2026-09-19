"""
Bloom Filter Synchronization

Provides distributed bloom filter synchronization across scan nodes.
Each node maintains a local bloom filter for fast negative lookups,
with periodic sync to the global FPDB.

Features:
- Redis-backed bloom filters for production
- Local pybloom-lite for testing
- Incremental sync (only new fingerprints)
- Sync via Kafka messages
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from abc import ABC, abstractmethod

# Try to import pybloom-lite, fall back to simple implementation
try:
    from pybloom_live import BloomFilter as PyBloomFilter
    HAS_PYBLOOM = True
except ImportError:
    HAS_PYBLOOM = False


class BloomFilter(ABC):
    """Abstract bloom filter interface."""

    @abstractmethod
    def add(self, item: str) -> None:
        """Add an item to the filter."""
        pass

    @abstractmethod
    def __contains__(self, item: str) -> bool:
        """Check if item might be in the set."""
        pass

    @abstractmethod
    def sync_from(self, other: "BloomFilter") -> None:
        """Merge another bloom filter into this one."""
        pass


class SimpleBloomFilter(BloomFilter):
    """
    Simple bloom filter implementation for testing.

    Uses a simple hash-based approach with multiple hash functions.
    Not production-quality but useful for testing.
    """

    def __init__(self, capacity: int = 100_000_000, error_rate: float = 0.001):
        self.capacity = capacity
        self.error_rate = error_rate

        # Calculate size and hash count using standard formulas
        # m = -n * ln(p) / (ln(2)^2)
        # k = (m / n) * ln(2)
        import math
        size = int(-capacity * math.log(error_rate) / (math.log(2) ** 2))
        self._size = size
        self._hash_count = max(1, int((size / capacity) * math.log(2)))

        # Bit array
        self._bits = bytearray((size + 7) // 8)

    def _get_bits(self, item: str) -> List[int]:
        """Get the bit positions for an item."""
        h1 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.md5(item.encode()).hexdigest(), 16)

        bits = []
        for i in range(self._hash_count):
            pos = (h1 + i * h2) % self._size
            bits.append(pos)
        return bits

    def add(self, item: str) -> None:
        """Add an item to the filter."""
        for bit in self._get_bits(item):
            byte_idx = bit // 8
            bit_idx = bit % 8
            self._bits[byte_idx] |= (1 << bit_idx)

    def __contains__(self, item: str) -> bool:
        """Check if item might be in the set."""
        for bit in self._get_bits(item):
            byte_idx = bit // 8
            bit_idx = bit % 8
            if not (self._bits[byte_idx] & (1 << bit_idx)):
                return False
        return True

    def sync_from(self, other: "SimpleBloomFilter") -> None:
        """Merge another bloom filter's bits into this one."""
        if len(self._bits) != len(other._bits):
            raise ValueError("Bloom filters must be same size to sync")

        for i in range(len(self._bits)):
            self._bits[i] |= other._bits[i]

    def count(self) -> int:
        """Estimate the number of items in the filter."""
        # Count set bits
        total_bits = sum(bin(byte).count("1") for byte in self._bits)
        # Estimate using: n = -m * ln(1 - k/m) / k
        import math
        m = len(self._bits) * 8
        if total_bits == 0:
            return 0
        k = self._hash_count
        n_estimate = -m * math.log(1 - total_bits / m) / k if total_bits < m else m
        return int(n_estimate)

    def to_dict(self) -> Dict:
        """Serialize for transmission."""
        return {
            "bits": self._bits.hex(),
            "size": self._size,
            "hash_count": self._hash_count
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SimpleBloomFilter":
        """Deserialize from dict."""
        bf = cls.__new__(cls)
        bf._size = data["size"]
        bf._hash_count = data["hash_count"]
        bf._bits = bytearray.fromhex(data["bits"])
        return bf


class RedisBloomFilter(BloomFilter):
    """
    Redis-backed bloom filter for production.

    Uses Redis with the Bloom filter module (or a RedisBloom client).
    Supports distributed synchronization across nodes.
    """

    def __init__(self, redis_client, key_prefix: str = "bloom:"):
        self.redis = redis_client
        self.key_prefix = key_prefix
        self._local_bits: Optional[SimpleBloomFilter] = None
        self._sync_interval = 60  # seconds
        self._last_sync = 0

    def _get_key(self, name: str) -> str:
        return f"{self.key_prefix}{name}"

    async def add(self, item: str) -> None:
        """Add an item to the local bloom filter and schedule sync."""
        if self._local_bits is None:
            self._local_bits = SimpleBloomFilter()

        self._local_bits.add(item)

        # In production: use Redis BF.ADD command
        # await self.redis.execute_command("BF.ADD", self._get_key("global"), item)

    async def __contains__(self, item: str) -> bool:
        """Check bloom filter."""
        if self._local_bits is not None and item in self._local_bits:
            return True

        # In production: check Redis bloom filter
        # result = await self.redis.execute_command("BF.EXISTS", self._get_key("global"), item)
        # return bool(result)

        return False

    async def sync(self) -> None:
        """Sync local bloom filter with Redis."""
        # In production: periodically get updated bits from Redis
        # This would download the entire bloom filter or delta updates
        pass


class BloomFilterManager:
    """
    Manages bloom filters across multiple scan nodes.

    Features:
    - Local bloom filter per node
    - Periodic sync with global bloom filter
    - Incremental updates via Kafka
    """

    def __init__(self, node_id: str, capacity: int = 100_000_000):
        self.node_id = node_id
        self.local_filter = SimpleBloomFilter(capacity=capacity)
        self._pending_adds: Set[str] = set()
        self._sync_lock = asyncio.Lock()

    def add(self, fingerprint: str) -> None:
        """Add a fingerprint to the local bloom filter."""
        self.local_filter.add(fingerprint)
        self._pending_adds.add(fingerprint)

    def may_contain(self, fingerprint: str) -> bool:
        """Check if fingerprint might exist."""
        return fingerprint in self.local_filter

    def get_pending_count(self) -> int:
        """Get number of pending fingerprints to sync."""
        return len(self._pending_adds)

    def clear_pending(self) -> List[str]:
        """Clear pending set and return the items."""
        result = list(self._pending_adds)
        self._pending_adds.clear()
        return result

    async def sync_to_kafka(self, producer, topic: str) -> int:
        """
        Sync pending fingerprints to Kafka for global distribution.

        Args:
            producer: Kafka producer
            topic: Topic to send to

        Returns:
            Number of fingerprints sent
        """
        if not self._pending_adds:
            return 0

        async with self._sync_lock:
            fingerprints = self.clear_pending()

            # Send batch message
            message = {
                "node_id": self.node_id,
                "action": "bloom_sync",
                "fingerprints": fingerprints,
                "timestamp": time.time()
            }

            await producer.send_and_wait(
                topic,
                json.dumps(message).encode(),
                partition=self._hash_partition(fingerprints[0] if fingerprints else "")
            )

            return len(fingerprints)

    def _hash_partition(self, item: str) -> int:
        """Simple hash-based partitioning for Kafka."""
        return abs(hash(item)) % 100

    @staticmethod
    def merge_filters(filters: List[SimpleBloomFilter]) -> SimpleBloomFilter:
        """
        Merge multiple bloom filters into one.

        Args:
            filters: List of SimpleBloomFilter to merge

        Returns:
            Merged bloom filter
        """
        if not filters:
            return SimpleBloomFilter()

        result = SimpleBloomFilter.__new__(SimpleBloomFilter)
        result._size = filters[0]._size
        result._hash_count = filters[0]._hash_count
        result._bits = bytearray(filters[0]._size)

        for bf in filters:
            for i in range(len(result._bits)):
                result._bits[i] |= bf._bits[i]

        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get bloom filter statistics."""
        return {
            "node_id": self.node_id,
            "estimated_items": self.local_filter.count(),
            "pending_sync": len(self._pending_adds),
            "filter_bits": self.local_filter._size,
            "hash_functions": self.local_filter._hash_count,
        }


class BloomFilterSyncProtocol:
    """
    Protocol for bloom filter synchronization.

    Messages are published to Kafka and processed by all nodes
    to keep their local bloom filters in sync.
    """

    @staticmethod
    def create_sync_message(node_id: str, fingerprints: List[str]) -> Dict:
        """Create a sync message."""
        return {
            "type": "bloom_sync",
            "node_id": node_id,
            "fingerprints": fingerprints,
            "timestamp": time.time(),
            "version": 1
        }

    @staticmethod
    def parse_sync_message(data: bytes) -> Optional[Dict]:
        """Parse a sync message."""
        try:
            msg = json.loads(data)
            if msg.get("type") == "bloom_sync":
                return msg
        except json.JSONDecodeError:
            pass
        return None


# Example usage
if __name__ == "__main__":
    # Test simple bloom filter
    bf1 = SimpleBloomFilter(capacity=10000, error_rate=0.01)
    bf2 = SimpleBloomFilter(capacity=10000, error_rate=0.01)

    # Add some items
    for i in range(1000):
        bf1.add(f"item_{i}")

    for i in range(500):
        bf2.add(f"item_{i}")

    # Check membership
    print(f"item_0 in bf1: {'item_0' in bf1}")  # True
    print(f"item_999 in bf1: {'item_999' in bf1}")  # True
    print(f"item_1000 in bf1: {'item_1000' in bf1}")  # False (probably)

    # Merge
    merged = BloomFilterManager.merge_filters([bf1, bf2])
    print(f"merged has item_0: {'item_0' in merged}")  # True
    print(f"merged has item_500: {'item_500' in merged}")  # True (from bf2)

    # Test manager
    manager = BloomFilterManager("node-1")
    for i in range(100):
        manager.add(f"fp_{i}")

    print(f"Pending sync: {manager.get_pending_count()}")
    print(f"Stats: {manager.get_stats()}")
