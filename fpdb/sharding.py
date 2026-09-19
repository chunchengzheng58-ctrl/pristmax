"""
Consistent Hashing Sharding for Global Fingerprint Database

Provides consistent hashing with virtual nodes for distributing
fingerprint records across ScyllaDB shards.

Features:
- 1024 virtual shards by default
- Minimal data movement on node add/remove (10% threshold)
- Support for shard-aware routing
"""

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import bisect


# Default configuration
DEFAULT_VIRTUAL_NODES = 150  # Virtual nodes per physical node
DEFAULT_TOTAL_SHARDS = 1024  # Total number of shards


@dataclass
class ShardInfo:
    """Information about a physical shard/node"""
    node_id: str
    host: str
    port: int
    virtual_nodes: List[int] = field(default_factory=list)
    is_healthy: bool = True
    last_heartbeat: float = 0.0


class ConsistentHashRing:
    """
    Consistent hashing ring for fingerprint sharding.

    Uses SHA-256 to map fingerprints to positions on the ring,
    then finds the first virtual node at or after that position.
    """

    def __init__(self, virtual_nodes: int = DEFAULT_VIRTUAL_NODES,
                 total_shards: int = DEFAULT_TOTAL_SHARDS):
        self.virtual_nodes_per_physical = virtual_nodes
        self.total_shards = total_shards
        self.nodes: Dict[str, ShardInfo] = {}
        self.ring: List[Tuple[int, str]] = []  # (position, node_id) sorted

    def _hash_position(self, key: str) -> int:
        """Map a key to a position on the ring (0 to 2^32-1)."""
        h = hashlib.sha256(key.encode()).digest()
        # Use first 4 bytes as unsigned int
        return int.from_bytes(h[:4], byteorder='big') % (2**32)

    def _hash_fingerprint(self, fingerprint: str) -> int:
        """Map a fingerprint to a shard index."""
        pos = self._hash_position(fingerprint)
        # Find the first node at or after this position
        if not self.ring:
            raise ValueError("No nodes in the ring")

        # Binary search for the first position >= pos
        positions = [p for p, _ in self.ring]
        idx = bisect.bisect_left(positions, pos)

        if idx >= len(self.ring):
            # Wrap around to first position
            idx = 0

        return self.ring[idx][1]  # Return node_id

    def add_node(self, node_id: str, host: str, port: int) -> None:
        """Add a physical node with virtual nodes."""
        if node_id in self.nodes:
            raise ValueError(f"Node {node_id} already exists")

        # Create virtual nodes for this physical node
        virtual_nodes = []
        for i in range(self.virtual_nodes_per_physical):
            vn_key = f"{node_id}::vn{i}"
            pos = self._hash_position(vn_key)
            virtual_nodes.append(pos)
            self.ring.append((pos, node_id))

        # Sort ring by position
        self.ring.sort(key=lambda x: x[0])

        # Store node info
        self.nodes[node_id] = ShardInfo(
            node_id=node_id,
            host=host,
            port=port,
            virtual_nodes=virtual_nodes
        )

    def remove_node(self, node_id: str) -> None:
        """Remove a physical node and all its virtual nodes."""
        if node_id not in self.nodes:
            return

        # Remove all virtual nodes for this physical
        self.ring = [(pos, nid) for pos, nid in self.ring if nid != node_id]
        del self.nodes[node_id]

    def get_shard(self, fingerprint: str) -> str:
        """Get the node_id responsible for a fingerprint."""
        return self._hash_fingerprint(fingerprint)

    def get_shard_for_key(self, key: str) -> str:
        """Get the node responsible for a generic key."""
        return self._hash_fingerprint(key)

    def get_all_shards(self) -> List[str]:
        """Get all node IDs in the ring."""
        return list(self.nodes.keys())

    def get_shard_info(self, node_id: str) -> Optional[ShardInfo]:
        """Get info about a specific shard."""
        return self.nodes.get(node_id)

    def update_heartbeat(self, node_id: str, timestamp: float) -> None:
        """Update the last heartbeat time for a node."""
        if node_id in self.nodes:
            self.nodes[node_id].last_heartbeat = timestamp

    def get_healthy_shards(self) -> List[str]:
        """Get list of healthy node IDs."""
        return [nid for nid, info in self.nodes.items() if info.is_healthy]

    def mark_unhealthy(self, node_id: str) -> None:
        """Mark a node as unhealthy."""
        if node_id in self.nodes:
            self.nodes[node_id].is_healthy = False

    def get_replica_nodes(self, fingerprint: str, replication_factor: int = 3) -> List[str]:
        """
        Get replica nodes for a fingerprint.
        Returns nodes in order of proximity on the ring.
        """
        if not self.ring:
            raise ValueError("No nodes in the ring")

        pos = self._hash_position(fingerprint)
        positions = [p for p, _ in self.ring]

        replicas = []
        seen_nodes: Set[str] = set()
        idx = bisect.bisect_left(positions, pos)

        # Collect unique nodes until we have enough replicas
        attempts = 0
        while len(replicas) < replication_factor and attempts < len(self.nodes):
            idx = idx % len(self.ring)
            node_id = self.ring[idx][1]

            if node_id not in seen_nodes and self.nodes[node_id].is_healthy:
                replicas.append(node_id)
                seen_nodes.add(node_id)

            idx += 1
            attempts += 1

        return replicas

    def get_stats(self) -> Dict:
        """Get statistics about the ring."""
        return {
            "total_physical_nodes": len(self.nodes),
            "total_virtual_nodes": len(self.ring),
            "virtual_nodes_per_physical": self.virtual_nodes_per_physical,
            "total_shards": self.total_shards,
            "healthy_nodes": len(self.get_healthy_shards()),
            "unhealthy_nodes": len(self.nodes) - len(self.get_healthy_shards())
        }


class ShardRouter:
    """
    Routes fingerprint operations to appropriate shards.

    Provides:
    - Shard-aware routing for fingerprint lookups
    - Batch routing for efficient multi-get operations
    - Replica routing for write operations
    """

    def __init__(self, ring: ConsistentHashRing):
        self.ring = ring

    def get_shard_for_fingerprint(self, fingerprint: str) -> str:
        """Get the primary shard for a fingerprint."""
        return self.ring.get_shard(fingerprint)

    def get_shards_for_fingerprints(self, fingerprints: List[str]) -> Dict[str, List[str]]:
        """
        Group fingerprints by their primary shard.

        Returns:
            Dict[shard_id, List[fingerprint]]
        """
        groups: Dict[str, List[str]] = {}
        for fp in fingerprints:
            shard = self.get_shard_for_fingerprint(fp)
            if shard not in groups:
                groups[shard] = []
            groups[shard].append(fp)
        return groups

    def get_replica_shards(self, fingerprint: str, replication_factor: int = 3) -> List[str]:
        """Get replica shards for a fingerprint."""
        return self.ring.get_replica_nodes(fingerprint, replication_factor)

    def get_preferred_shard(self, fingerprint: str, node_id: str) -> str:
        """
        Get the preferred shard, preferring the specified node if it has the fingerprint.
        Used for data locality during processing.
        """
        primary = self.get_shard_for_fingerprint(fingerprint)

        # If the specified node has this fingerprint, use it
        if primary == node_id:
            return primary

        # Otherwise check if this node is a replica
        replicas = self.get_replica_shards(fingerprint)
        if node_id in replicas:
            return node_id

        # Fall back to primary
        return primary


# Example usage
def create_test_ring() -> ConsistentHashRing:
    """Create a test ring with sample nodes."""
    ring = ConsistentHashRing(virtual_nodes=50, total_shards=256)

    # Add sample nodes
    for i in range(3):
        ring.add_node(f"node-{i}", f"192.168.1.{100+i}", 9042)

    return ring


if __name__ == "__main__":
    # Test the sharding
    ring = create_test_ring()

    print("Ring stats:", ring.get_stats())
    print()

    # Test fingerprint routing
    test_fps = [
        "a" * 64,  # All 'a'
        "b" * 64,  # All 'b'
        "abc123" + "0" * 58,
    ]

    for fp in test_fps:
        shard = ring.get_shard(fp)
        replicas = ring.get_replica_nodes(fp, 3)
        print(f"Fingerprint: {fp[:16]}... -> Shard: {shard}, Replicas: {replicas}")
