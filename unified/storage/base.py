"""
Pristmax Storage Base Classes

定义存储适配器的抽象基类和核心数据结构
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Dict, Any, Callable
from enum import Enum
import hashlib
import os


class StorageType(Enum):
    """存储类型枚举"""
    LOCAL_DISK = "local_disk"
    NAS = "nas"
    USB = "usb"
    CLOUD = "cloud"
    RAID = "raid"


class HashAlgorithm(Enum):
    """哈希算法枚举"""
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"
    XXHASH64 = "xxh64"


@dataclass
class StorageInfo:
    """
    存储设备信息

    Attributes:
        name: 存储名称 (如 "本地磁盘 C:" )
        storage_type: 存储类型
        path: 挂载点或访问路径
        total_size: 总容量 (bytes)
        used_size: 已用空间 (bytes)
        free_size: 剩余空间 (bytes)
        is_mounted: 是否已挂载
        status: 状态 (healthy/error/offline)
        metadata: 额外元数据
    """
    name: str
    storage_type: StorageType
    path: str
    total_size: int = 0
    used_size: int = 0
    free_size: int = 0
    is_mounted: bool = True
    status: str = "healthy"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def usage_percent(self) -> float:
        """计算使用率百分比"""
        if self.total_size == 0:
            return 0.0
        return (self.used_size / self.total_size) * 100

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'name': self.name,
            'type': self.storage_type.value,
            'path': self.path,
            'total_size': self.total_size,
            'used_size': self.used_size,
            'free_size': self.free_size,
            'usage_percent': round(self.usage_percent, 1),
            'is_mounted': self.is_mounted,
            'status': self.status,
            'metadata': self.metadata,
        }


@dataclass
class FileInfo:
    """
    文件信息

    Attributes:
        path: 文件完整路径
        relative_path: 相对于存储根目录的路径
        size: 文件大小 (bytes)
        modified_time: 修改时间 (Unix timestamp)
        hash: 文件哈希值 (可选)
        hash_algorithm: 哈希算法
        storage_type: 所属存储类型
        is_directory: 是否为目录
        extension: 文件扩展名
    """
    path: str
    relative_path: str
    size: int
    modified_time: float
    hash: Optional[str] = None
    hash_algorithm: str = "sha256"
    storage_type: Optional[StorageType] = None
    is_directory: bool = False
    extension: str = ""

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'path': self.path,
            'relative_path': self.relative_path,
            'size': self.size,
            'modified_time': self.modified_time,
            'hash': self.hash,
            'hash_algorithm': self.hash_algorithm,
            'type': self.storage_type.value if self.storage_type else None,
            'is_directory': self.is_directory,
            'extension': self.extension,
        }


@dataclass
class ScanProgress:
    """
    扫描进度信息

    Attributes:
        current: 当前已扫描文件数
        total: 预计总文件数
        current_path: 当前扫描路径
        bytes_scanned: 已扫描的数据量
        start_time: 扫描开始时间
        elapsed_seconds: 已耗时(秒)
    """
    current: int = 0
    total: int = 0
    current_path: str = ""
    bytes_scanned: int = 0
    start_time: float = 0.0
    elapsed_seconds: float = 0.0

    @property
    def percent(self) -> float:
        """完成百分比"""
        if self.total == 0:
            return 0.0
        return (self.current / self.total) * 100

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'current': self.current,
            'total': self.total,
            'percent': round(self.percent, 1),
            'current_path': self.current_path,
            'bytes_scanned': self.bytes_scanned,
            'elapsed_seconds': round(self.elapsed_seconds, 1),
        }


class StorageAdapter(ABC):
    """
    存储适配器抽象基类

    所有存储类型适配器必须继承此类并实现抽象方法

    Example:
        class LocalDiskAdapter(StorageAdapter):
            @property
            def storage_type(self) -> StorageType:
                return StorageType.LOCAL_DISK

            def connect(self) -> bool:
                self._is_connected = True
                return True

            def disconnect(self):
                self._is_connected = False

            def get_info(self) -> StorageInfo:
                return StorageInfo(...)
    """

    def __init__(self, config: dict):
        """
        初始化适配器

        Args:
            config: 适配器配置字典
        """
        self.config = config
        self._is_connected = False
        self._storage_id = config.get('id', '')
        self._storage_name = config.get('name', '')

    @property
    @abstractmethod
    def storage_type(self) -> StorageType:
        """
        返回存储类型

        Returns:
            StorageType: 存储类型枚举值
        """
        pass

    @property
    def storage_id(self) -> str:
        """获取存储 ID"""
        return self._storage_id

    @property
    def storage_name(self) -> str:
        """获取存储名称"""
        return self._storage_name

    @abstractmethod
    def connect(self) -> bool:
        """
        连接到存储

        Returns:
            bool: 连接是否成功
        """
        pass

    @abstractmethod
    def disconnect(self):
        """
        断开存储连接
        """
        pass

    @abstractmethod
    def get_info(self) -> StorageInfo:
        """
        获取存储信息

        Returns:
            StorageInfo: 存储设备信息
        """
        pass

    @abstractmethod
    def scan(
        self,
        path: str = "/",
        recursive: bool = True,
        progress_callback: Optional[Callable[[ScanProgress], None]] = None
    ) -> Iterator[FileInfo]:
        """
        扫描存储路径

        Args:
            path: 扫描起始路径
            recursive: 是否递归扫描子目录
            progress_callback: 进度回调函数

        Yields:
            FileInfo: 文件信息对象
        """
        pass

    @abstractmethod
    def read_file(self, path: str, offset: int = 0, size: Optional[int] = None) -> bytes:
        """
        读取文件内容

        Args:
            path: 文件路径
            offset: 读取偏移量
            size: 读取大小 (None 表示读取全部)

        Returns:
            bytes: 文件内容
        """
        pass

    @abstractmethod
    def compute_hash(
        self,
        path: str,
        algorithm: str = "sha256",
        chunk_size: int = 8192
    ) -> str:
        """
        计算文件哈希

        Args:
            path: 文件路径
            algorithm: 哈希算法 (md5/sha1/sha256)
            chunk_size: 每次读取块大小

        Returns:
            str: 文件哈希值 (十六进制字符串)
        """
        pass

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._is_connected

    def _validate_path(self, path: str) -> bool:
        """
        验证路径是否有效

        Args:
            path: 待验证的路径

        Returns:
            bool: 路径是否有效
        """
        if not path:
            return False
        # 子类可重写以添加特定验证逻辑
        return True

    def _get_file_extension(self, path: str) -> str:
        """获取文件扩展名"""
        return os.path.splitext(path)[1].lower().lstrip('.')

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self._storage_id} type={self.storage_type.value}>"
