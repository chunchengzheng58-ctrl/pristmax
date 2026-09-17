"""
M3 Storage Module: Storage Connectors

M3 核心模块: 存储连接器。

支持类型:
- LocalConnector: 本地磁盘
- NASConnector: NAS (SMB/NFS)
- CloudConnector: 云存储 (S3)
"""

from .storage.connectors import (
    StorageConnector,
    StorageKind,
    StorageStats,
    FileInfo,
    LocalConnector,
    NASConnector,
    CloudConnector,
    ConnectorFactory
)

__all__ = [
    'StorageConnector',
    'StorageKind',
    'StorageStats',
    'FileInfo',
    'LocalConnector',
    'NASConnector',
    'CloudConnector',
    'ConnectorFactory',
]
