"""
M4 Distributed Module: Distributed Storage Coordination

M4 核心模块:
- ConsistentHash: 一致性哈希
- StorageNode: 存储节点
- DataChunk: 数据分片
- DistributedCoordinator: 分布式协调器
"""

from .distributed.coordinator import (
    NodeState,
    StorageNode,
    DataChunk,
    ConsistentHash,
    DistributedCoordinator
)

__all__ = [
    'NodeState',
    'StorageNode',
    'DataChunk',
    'ConsistentHash',
    'DistributedCoordinator',
]
