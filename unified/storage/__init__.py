"""
Pristmax Storage Abstraction Layer

统一存储抽象层，支持多种存储类型的适配器
"""
from .base import StorageType, StorageInfo, FileInfo, ScanProgress, StorageAdapter
from .manager import StorageManager, storage_manager
from .registry import StorageRegistry
from .scanners import UnifiedScanner, unified_scanner

# 导入所有适配器 (触发自动注册)
from .adapters import (
    LocalDiskAdapter,
    NASAdapter,
    USBAdapter,
    CloudAdapter,
    RAIDAdapter,
)

__all__ = [
    # 基类
    'StorageType',
    'StorageInfo',
    'FileInfo',
    'ScanProgress',
    'StorageAdapter',
    # 管理器
    'StorageManager',
    'storage_manager',
    # 注册表
    'StorageRegistry',
    # 扫描器
    'UnifiedScanner',
    'unified_scanner',
    # 适配器
    'LocalDiskAdapter',
    'NASAdapter',
    'USBAdapter',
    'CloudAdapter',
    'RAIDAdapter',
]
