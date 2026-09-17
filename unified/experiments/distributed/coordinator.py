"""
M4 Distributed Module: Distributed Storage Coordination

M4 核心模块: 分布式存储协调。

功能:
- 节点管理
- 数据分片
- 一致性哈希
- 数据修复
- 副本管理
"""
import hashlib
import json
import socket
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
from datetime import datetime


class NodeState(Enum):
    """节点状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    RECOVERING = "recovering"


@dataclass
class StorageNode:
    """存储节点"""
    node_id: str
    host: str
    port: int

    # 状态
    state: NodeState = NodeState.ACTIVE

    # 容量
    capacity_bytes: int = 0
    used_bytes: int = 0

    # 虚拟节点数 (用于一致性哈希)
    virtual_nodes: int = 100

    # 时间戳
    last_heartbeat: str = ""

    @property
    def available_bytes(self) -> int:
        return max(0, self.capacity_bytes - self.used_bytes)

    @property
    def usage_percent(self) -> float:
        if self.capacity_bytes == 0:
            return 0
        return (self.used_bytes / self.capacity_bytes) * 100

    def to_dict(self) -> dict:
        return {
            'node_id': self.node_id,
            'host': self.host,
            'port': self.port,
            'state': self.state.value,
            'capacity_bytes': self.capacity_bytes,
            'used_bytes': self.used_bytes,
            'virtual_nodes': self.virtual_nodes,
            'last_heartbeat': self.last_heartbeat
        }


@dataclass
class DataChunk:
    """数据分片"""
    chunk_id: str
    content_hash: str
    size: int

    # 副本位置
    replicas: List[Tuple[str, str]] = field(default_factory=list)  # [(node_id, path), ...]

    # 分片信息
    primary_node: str = ""  # 主副本节点

    def to_dict(self) -> dict:
        return {
            'chunk_id': self.chunk_id,
            'content_hash': self.content_hash,
            'size': self.size,
            'replicas': self.replicas,
            'primary_node': self.primary_node
        }


class ConsistentHash:
    """
    一致性哈希

    用于数据分片和节点分布
    """

    def __init__(self, virtual_nodes: int = 100):
        self.virtual_nodes = virtual_nodes
        self.ring: Dict[int, str] = {}  # hash -> node_id
        self.sorted_keys: List[int] = []

    def add_node(self, node: StorageNode):
        """添加节点到哈希环"""
        for i in range(node.virtual_nodes):
            key = self._hash(f"{node.node_id}:{i}")
            self.ring[key] = node.node_id

        self._sort_keys()

    def remove_node(self, node_id: str):
        """从哈希环移除节点"""
        for i in range(self.virtual_nodes):
            key = self._hash(f"{node_id}:{i}")
            if key in self.ring:
                del self.ring[key]

        self._sort_keys()

    def get_node(self, key: str) -> str:
        """获取 key 所属的节点"""
        if not self.ring:
            return ""

        hash_val = self._hash(key)

        # 找到第一个 >= hash_val 的节点
        for k in self.sorted_keys:
            if k >= hash_val:
                return self.ring[k]

        # 回到起点
        return self.ring[self.sorted_keys[0]]

    def get_nodes_for_key(self, key: str, replicas: int = 3) -> List[str]:
        """获取 key 的多个副本节点"""
        hash_val = self._hash(key)
        nodes = []
        seen = set()

        for k in self.sorted_keys:
            if k >= hash_val:
                node_id = self.ring[k]
                if node_id not in seen:
                    nodes.append(node_id)
                    seen.add(node_id)
                    if len(nodes) >= replicas:
                        return nodes

        # 回到起点
        for k in self.sorted_keys:
            node_id = self.ring[k]
            if node_id not in seen:
                nodes.append(node_id)
                seen.add(node_id)
                if len(nodes) >= replicas:
                    return nodes

        return nodes

    def _hash(self, key: str) -> int:
        """计算哈希值"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def _sort_keys(self):
        """排序键"""
        self.sorted_keys = sorted(self.ring.keys())


class DistributedCoordinator:
    """
    分布式协调器

    管理节点、分片、副本
    """

    def __init__(
        self,
        replication_factor: int = 3,
        min_nodes: int = 2
    ):
        self.replication_factor = replication_factor
        self.min_nodes = min_nodes

        # 节点管理
        self.nodes: Dict[str, StorageNode] = {}
        self.hash_ring = ConsistentHash()

        # 分片管理
        self.chunks: Dict[str, DataChunk] = {}  # chunk_id -> DataChunk

        # 节点映射
        self.node_chunks: Dict[str, Set[str]] = {}  # node_id -> set of chunk_ids

    def add_node(self, node: StorageNode) -> bool:
        """
        添加存储节点

        Args:
            node: 存储节点

        Returns:
            是否成功
        """
        if node.node_id in self.nodes:
            return False

        node.last_heartbeat = datetime.now().isoformat()
        self.nodes[node.node_id] = node
        self.hash_ring.add_node(node)
        self.node_chunks[node.node_id] = set()

        print(f"[Distributed] Node added: {node.node_id} ({node.host}:{node.port})")
        return True

    def remove_node(self, node_id: str) -> bool:
        """移除存储节点"""
        if node_id not in self.nodes:
            return False

        # 转移数据
        self._migrate_data(node_id)

        # 从哈希环移除
        self.hash_ring.remove_node(node_id)
        del self.nodes[node_id]
        del self.node_chunks[node_id]

        print(f"[Distributed] Node removed: {node_id}")
        return True

    def _migrate_data(self, from_node_id: str):
        """迁移数据"""
        chunks_to_migrate = list(self.node_chunks.get(from_node_id, set()))

        for chunk_id in chunks_to_migrate:
            chunk = self.chunks.get(chunk_id)
            if not chunk:
                continue

            # 选择新节点
            new_nodes = self.hash_ring.get_nodes_for_key(
                chunk.content_hash,
                self.replication_factor
            )

            if from_node_id in new_nodes:
                new_nodes.remove(from_node_id)

            # 更新副本
            chunk.replicas = [
                (n, chunk.replicas[0][1])  # 保留路径，只是换节点
                for n in new_nodes[:self.replication_factor]
            ]
            if chunk.replicas:
                chunk.primary_node = chunk.replicas[0][0]

        print(f"[Distributed] Migrated {len(chunks_to_migrate)} chunks from {from_node_id}")

    def store_chunk(
        self,
        chunk_id: str,
        content_hash: str,
        size: int,
        data_path: str
    ) -> bool:
        """
        存储分片

        Args:
            chunk_id: 分片 ID
            content_hash: 内容哈希
            size: 大小
            data_path: 数据路径

        Returns:
            是否成功
        """
        if not self.nodes:
            print("[Distributed] No nodes available")
            return False

        # 选择节点
        nodes = self.hash_ring.get_nodes_for_key(
            content_hash,
            self.replication_factor
        )

        if len(nodes) < self.replication_factor:
            print(f"[Distributed] Not enough nodes: need {self.replication_factor}, have {len(nodes)}")
            return False

        # 创建分片
        chunk = DataChunk(
            chunk_id=chunk_id,
            content_hash=content_hash,
            size=size,
            replicas=[(n, f"{data_path}/{chunk_id}") for n in nodes],
            primary_node=nodes[0]
        )

        self.chunks[chunk_id] = chunk

        # 更新节点映射
        for node_id in nodes:
            if node_id in self.node_chunks:
                self.node_chunks[node_id].add(chunk_id)

        # 更新节点使用量
        for node_id in nodes:
            if node_id in self.nodes:
                self.nodes[node_id].used_bytes += size

        print(f"[Distributed] Chunk stored: {chunk_id} on {nodes}")
        return True

    def get_chunk_locations(self, chunk_id: str) -> List[Tuple[str, str]]:
        """获取分片位置"""
        chunk = self.chunks.get(chunk_id)
        return chunk.replicas if chunk else []

    def repair_chunk(self, chunk_id: str) -> bool:
        """
        修复分片

        从其他副本恢复数据
        """
        chunk = self.chunks.get(chunk_id)
        if not chunk:
            return False

        # 检查哪些节点不可用
        available_replicas = [
            (n, p) for n, p in chunk.replicas
            if n in self.nodes and self.nodes[n].state == NodeState.ACTIVE
        ]

        if len(available_replicas) < 1:
            print(f"[Distributed] No available replicas for {chunk_id}")
            return False

        # 找到新节点
        all_nodes = set(self.nodes.keys())
        current_nodes = {n for n, _ in chunk.replicas}
        missing_nodes = all_nodes - current_nodes

        if not missing_nodes:
            print(f"[Distributed] No missing nodes for {chunk_id}")
            return True

        # 重新分配副本
        new_node = list(missing_nodes)[0]
        new_replicas = available_replicas[:self.replication_factor - 1] + [(new_node, f"{chunk.replicas[0][1]}")]

        chunk.replicas = new_replicas
        if chunk.replicas:
            chunk.primary_node = new_replicas[0][0]

        print(f"[Distributed] Chunk repaired: {chunk_id} on {new_replicas}")
        return True

    def get_node_stats(self, node_id: str) -> Optional[Dict]:
        """获取节点统计"""
        node = self.nodes.get(node_id)
        if not node:
            return None

        return {
            'node_id': node.node_id,
            'state': node.state.value,
            'capacity_gb': node.capacity_bytes / 1024**3,
            'used_gb': node.used_bytes / 1024**3,
            'available_gb': node.available_bytes / 1024**3,
            'usage_percent': node.usage_percent,
            'chunks': len(self.node_chunks.get(node_id, set()))
        }

    def get_cluster_stats(self) -> Dict:
        """获取集群统计"""
        total_capacity = sum(n.capacity_bytes for n in self.nodes.values())
        total_used = sum(n.used_bytes for n in self.nodes.values())

        return {
            'total_nodes': len(self.nodes),
            'active_nodes': sum(1 for n in self.nodes.values() if n.state == NodeState.ACTIVE),
            'total_chunks': len(self.chunks),
            'total_capacity_gb': total_capacity / 1024**3,
            'total_used_gb': total_used / 1024**3,
            'usage_percent': (total_used / total_capacity * 100) if total_capacity else 0
        }


def main():
    """演示"""
    coord = DistributedCoordinator(replication_factor=2, min_nodes=1)

    # 添加节点
    for i in range(3):
        node = StorageNode(
            node_id=f"node-{i}",
            host=f"192.168.1.{100+i}",
            port=8000,
            capacity_bytes=10 * 1024**3  # 10 GB
        )
        coord.add_node(node)

    # 存储数据
    coord.store_chunk(
        chunk_id="chunk-001",
        content_hash="hash123",
        size=1024,
        data_path="/data/chunks"
    )

    # 获取集群状态
    print(f"\n[Distributed] Cluster stats: {coord.get_cluster_stats()}")


if __name__ == '__main__':
    main()
