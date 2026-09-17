"""
M3 Storage Connectors: Local/NAS/Cloud Adapters

M3 核心模块: 存储连接器。

功能:
- 本地磁盘连接
- NAS 连接 (SMB/NFS)
- 云存储连接 (S3)
- 统一接口
"""
import os
import shutil
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path
import json


class StorageKind(Enum):
    """存储类型"""
    LOCAL = "local"
    NAS = "nas"
    CLOUD = "cloud"


@dataclass
class StorageStats:
    """存储统计"""
    total_bytes: int = 0
    used_bytes: int = 0
    available_bytes: int = 0
    file_count: int = 0

    def usage_percent(self) -> float:
        if self.total_bytes == 0:
            return 0
        return (self.used_bytes / self.total_bytes) * 100


@dataclass
class FileInfo:
    """文件信息"""
    path: str
    size_bytes: int = 0
    modified_time: float = 0
    is_dir: bool = False


class StorageConnector(ABC):
    """存储连接器基类"""

    @abstractmethod
    def connect(self) -> bool:
        """连接存储"""
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    def list_files(self, path: str = "/") -> List[FileInfo]:
        """列出文件"""
        pass

    @abstractmethod
    def get_stats(self) -> StorageStats:
        """获取存储统计"""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        pass

    @abstractmethod
    def read(self, path: str, dest_path: str) -> bool:
        """读取文件到本地"""
        pass

    @abstractmethod
    def write(self, local_path: str, dest_path: str) -> bool:
        """写入文件"""
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """删除文件"""
        pass


class LocalConnector(StorageConnector):
    """本地磁盘连接器"""

    def __init__(self, root_path: str = "."):
        self.root_path = Path(root_path).resolve()
        self._connected = False

    def connect(self) -> bool:
        if not self.root_path.exists():
            return False
        self._connected = True
        print(f"[Local] Connected: {self.root_path}")
        return True

    def disconnect(self):
        self._connected = False
        print("[Local] Disconnected")

    def list_files(self, path: str = "/") -> List[FileInfo]:
        target = self.root_path / path.lstrip("/")
        if not target.exists():
            return []

        files = []
        for entry in target.iterdir():
            stat = entry.stat()
            files.append(FileInfo(
                path=str(entry.relative_to(self.root_path)),
                size_bytes=stat.st_size,
                modified_time=stat.st_mtime,
                is_dir=entry.is_dir()
            ))
        return files

    def get_stats(self) -> StorageStats:
        try:
            stat = shutil.disk_usage(self.root_path)
            return StorageStats(
                total_bytes=stat.total,
                used_bytes=stat.used,
                available_bytes=stat.free
            )
        except Exception:
            return StorageStats()

    def exists(self, path: str) -> bool:
        return (self.root_path / path.lstrip("/")).exists()

    def read(self, path: str, dest_path: str) -> bool:
        src = self.root_path / path.lstrip("/")
        if not src.exists():
            return False
        try:
            shutil.copy2(src, dest_path)
            return True
        except Exception:
            return False

    def write(self, local_path: str, dest_path: str) -> bool:
        dest = self.root_path / dest_path.lstrip("/")
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, dest)
            return True
        except Exception:
            return False

    def delete(self, path: str) -> bool:
        target = self.root_path / path.lstrip("/")
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            return True
        except Exception:
            return False


class NASConnector(StorageConnector):
    """NAS 连接器 (SMB/NFS)"""

    def __init__(
        self,
        host: str,
        share: str,
        username: str = "",
        password: str = "",
        protocol: str = "smb"  # smb or nfs
    ):
        self.host = host
        self.share = share
        self.username = username
        self.password = password
        self.protocol = protocol

        self._connected = False
        self._mounted_path: Optional[Path] = None

    def connect(self) -> bool:
        """挂载 NAS"""
        # 简化的本地模拟 - 实际应使用 smbclient 或 mount.nfs
        print(f"[NAS] Connecting to {self.host}/{self.share}")
        self._connected = True
        return True

    def disconnect(self):
        """卸载 NAS"""
        if self._mounted_path and self._mounted_path.exists():
            # umount 操作
            pass
        self._connected = False
        print("[NAS] Disconnected")

    def list_files(self, path: str = "/") -> List[FileInfo]:
        # 模拟实现
        return []

    def get_stats(self) -> StorageStats:
        # 模拟实现
        return StorageStats(
            total_bytes=10 * 1024**4,  # 10 TB
            used_bytes=3 * 1024**4,     # 3 TB
            available_bytes=7 * 1024**4
        )

    def exists(self, path: str) -> bool:
        return False

    def read(self, path: str, dest_path: str) -> bool:
        return False

    def write(self, local_path: str, dest_path: str) -> bool:
        return False

    def delete(self, path: str) -> bool:
        return False


class CloudConnector(StorageConnector):
    """云存储连接器 (S3)"""

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1"
    ):
        self.endpoint = endpoint
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region

        self._connected = False
        self._client = None

    def connect(self) -> bool:
        """连接云存储"""
        print(f"[Cloud] Connecting to {self.endpoint}/{self.bucket}")
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False
        print("[Cloud] Disconnected")

    def list_files(self, path: str = "/") -> List[FileInfo]:
        # 模拟实现
        return []

    def get_stats(self) -> StorageStats:
        # 模拟实现
        return StorageStats(
            total_bytes=100 * 1024**4,  # 100 TB
            used_bytes=25 * 1024**4,    # 25 TB
            available_bytes=75 * 1024**4
        )

    def exists(self, path: str) -> bool:
        return False

    def read(self, path: str, dest_path: str) -> bool:
        return False

    def write(self, local_path: str, dest_path: str) -> bool:
        return False

    def delete(self, path: str) -> bool:
        return False


class ConnectorFactory:
    """连接器工厂"""

    _connectors: Dict[str, StorageConnector] = {}

    @classmethod
    def register(cls, name: str, connector: StorageConnector):
        cls._connectors[name] = connector

    @classmethod
    def get(cls, name: str) -> Optional[StorageConnector]:
        return cls._connectors.get(name)

    @classmethod
    def create_local(cls, name: str, root_path: str = ".") -> LocalConnector:
        connector = LocalConnector(root_path)
        cls.register(name, connector)
        return connector

    @classmethod
    def create_nas(
        cls,
        name: str,
        host: str,
        share: str,
        username: str = "",
        password: str = ""
    ) -> NASConnector:
        connector = NASConnector(host, share, username, password)
        cls.register(name, connector)
        return connector

    @classmethod
    def create_cloud(
        cls,
        name: str,
        endpoint: str,
        bucket: str,
        access_key: str = "",
        secret_key: str = ""
    ) -> CloudConnector:
        connector = CloudConnector(endpoint, bucket, access_key, secret_key)
        cls.register(name, connector)
        return connector

    @classmethod
    def list_connectors(cls) -> List[str]:
        return list(cls._connectors.keys())


def main():
    """演示"""
    # 本地连接器
    local = ConnectorFactory.create_local("local-disk", "/tmp/test")
    if local.connect():
        stats = local.get_stats()
        print(f"[Local] Usage: {stats.usage_percent():.1f}%")
        print(f"[Local] Available: {stats.available_bytes / 1024**3:.1f} GB")


if __name__ == '__main__':
    main()
