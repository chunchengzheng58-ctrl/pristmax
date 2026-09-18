"""
M4 Dedup Module: Safe Deduplication with Data Protection

安全去重模块:
- 引用计数保护 (绝不删除仍有引用的块)
- 用户授权机制 (删除操作需授权)
- 审计日志
- 备份保护
"""

from .chunker import (
    Chunk,
    FastCDC,
    ParallelChunker,
    chunk_file_with_dedup
)

from .index import (
    ChunkRef,
    DedupIndexSafe,
    DedupStats,
    AuditLog,
    OperationType,
    DeleteAuthorizationStatus
)

__all__ = [
    'Chunk',
    'FastCDC',
    'ParallelChunker',
    'chunk_file_with_dedup',
    'ChunkRef',
    'DedupIndexSafe',
    'DedupStats',
    'AuditLog',
    'OperationType',
    'DeleteAuthorizationStatus',
]
