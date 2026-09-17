"""
Local Disk Adapter

本地硬盘存储适配器，支持 SSD/HDD 磁盘
"""
import os
import time
import shutil
from pathlib import Path
from typing import Iterator, Optional, List

from storage.base import (
    StorageType, StorageInfo, FileInfo, ScanProgress,
    StorageAdapter
)


class LocalDiskAdapter(StorageAdapter):
    """
    本地磁盘存储适配器

    用于扫描和管理本地硬盘上的文件，支持:
    - 多挂载点扫描
    - 排除路径过滤
    - 文件哈希计算
    - 进度跟踪

    Example:
        adapter = LocalDiskAdapter({
            'id': 'local-001',
            'name': '本地磁盘 (C:)',
            'mount_points': ['C:\\', 'D:\\'],
            'exclude_paths': ['C:\\Windows', 'C:\\$Recycle.Bin']
        })
        adapter.connect()
        info = adapter.get_info()
        for file in adapter.scan('C:\\'):
            print(file.path, file.size)
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._mount_points: List[str] = config.get('mount_points', [])
        self._exclude_paths: List[str] = config.get('exclude_paths', [])
        self._exclude_extensions: List[str] = config.get('exclude_extensions', [])
        self._min_file_size: int = config.get('min_file_size', 0)

        # Windows 默认排除
        if not self._exclude_paths and os.name == 'nt':
            self._exclude_paths = [
                'C:\\Windows',
                'C:\\$Recycle.Bin',
                'C:\\System Volume Information',
                'C:\\Windows\\SoftwareDistribution\\Download',
                'C:\\Windows\\WinSxS',
                'C:\\ProgramData\\Microsoft\\Windows\\WER',
                'C:\\Windows\\Logs',
            ]

    @property
    def storage_type(self) -> StorageType:
        return StorageType.LOCAL_DISK

    def connect(self) -> bool:
        """连接到本地磁盘 (始终成功)"""
        self._is_connected = True
        return True

    def disconnect(self):
        """断开连接"""
        self._is_connected = False

    def get_info(self) -> StorageInfo:
        """
        获取磁盘信息

        Returns:
            StorageInfo: 磁盘使用信息
        """
        if not self._mount_points:
            # 如果没有指定挂载点，返回所有可用磁盘
            return self._get_all_disks_info()

        # 使用第一个挂载点作为主磁盘
        main_path = self._mount_points[0]
        return self._get_disk_info(main_path)

    def _get_disk_info(self, path: str) -> StorageInfo:
        """获取指定路径的磁盘信息"""
        try:
            # Windows 使用 nt.stat Franklin
            if os.name == 'nt':
                # 获取驱动器字母
                drive = os.path.splitdrive(path)[0]
                if not drive:
                    drive = os.path.splitdrive(os.getcwd())[0]
            else:
                drive = path

            usage = shutil.disk_usage(path if os.path.exists(path) else os.path.dirname(path) or '/')

            return StorageInfo(
                name=self._storage_name or f"本地磁盘 ({drive})",
                storage_type=StorageType.LOCAL_DISK,
                path=path,
                total_size=usage.total,
                used_size=usage.used,
                free_size=usage.free,
                is_mounted=True,
                status="healthy",
                metadata={
                    'drive': drive,
                    'fstype': 'NTFS' if os.name == 'nt' else 'ext4',
                }
            )
        except Exception as e:
            return StorageInfo(
                name=self._storage_name or "本地磁盘",
                storage_type=StorageType.LOCAL_DISK,
                path=path,
                status="error",
                metadata={'error': str(e)}
            )

    def _get_all_disks_info(self) -> StorageInfo:
        """获取所有磁盘的汇总信息"""
        total_size = 0
        total_used = 0
        total_free = 0

        if os.name == 'nt':
            # Windows: 遍历 A-Z 驱动器
            for letter in range(ord('A'), ord('Z') + 1):
                drive = f"{chr(letter)}:\\"
                try:
                    if os.path.exists(drive):
                        usage = shutil.disk_usage(drive)
                        total_size += usage.total
                        total_used += usage.used
                        total_free += usage.free
                except:
                    pass
        else:
            # Unix: 使用 /Volumes 或根目录
            try:
                usage = shutil.disk_usage('/')
                total_size = usage.total
                total_used = usage.used
                total_free = usage.free
            except:
                pass

        return StorageInfo(
            name=self._storage_name or "本地磁盘",
            storage_type=StorageType.LOCAL_DISK,
            path=self._mount_points[0] if self._mount_points else "/",
            total_size=total_size,
            used_size=total_used,
            free_size=total_free,
            is_mounted=True,
            status="healthy" if total_size > 0 else "error",
        )

    def scan(
        self,
        path: str = "/",
        recursive: bool = True,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """
        扫描指定路径

        Args:
            path: 扫描路径
            recursive: 是否递归扫描子目录
            progress_callback: 进度回调函数

        Yields:
            FileInfo: 文件信息对象
        """
        if not self._is_connected:
            self.connect()

        # 确定实际扫描路径
        scan_paths = [path] if path != "/" else self._mount_points
        if not scan_paths:
            scan_paths = [os.getcwd()]

        total_files = 0

        for scan_path in scan_paths:
            if not os.path.exists(scan_path):
                continue

            if os.path.isfile(scan_path):
                # 单文件
                file_info = self._create_file_info(scan_path, scan_path)
                if file_info and self._should_include(file_info):
                    yield file_info
                continue

            # 目录扫描
            for file_info in self._scan_directory(scan_path, recursive, progress_callback):
                if self._should_include(file_info):
                    total_files += 1
                    yield file_info

    def _scan_directory(
        self,
        root_path: str,
        recursive: bool,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """递归扫描目录"""
        try:
            for entry in os.scandir(root_path):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if recursive and not self._should_exclude(entry.path):
                            yield from self._scan_directory(entry.path, recursive, progress_callback)
                    elif entry.is_file(follow_symlinks=False):
                        file_info = self._create_file_info(entry.path, root_path)
                        if file_info:
                            yield file_info

                except (PermissionError, OSError):
                    # 跳过无权限访问的文件/目录
                    continue

        except (PermissionError, OSError):
            pass

    def _create_file_info(self, file_path: str, root_path: str) -> Optional[FileInfo]:
        """创建文件信息对象"""
        try:
            stat = os.stat(file_path, follow_symlinks=False)

            # 计算相对路径
            try:
                relative_path = os.path.relpath(file_path, root_path)
            except ValueError:
                relative_path = file_path

            return FileInfo(
                path=file_path,
                relative_path=relative_path,
                size=stat.st_size,
                modified_time=stat.st_mtime,
                storage_type=StorageType.LOCAL_DISK,
                is_directory=False,
                extension=self._get_file_extension(file_path),
            )
        except (PermissionError, OSError, FileNotFoundError):
            return None

    def _should_include(self, file_info: FileInfo) -> bool:
        """检查文件是否应该包含"""
        # 最小文件大小
        if file_info.size < self._min_file_size:
            return False

        # 排除扩展名
        if file_info.extension and file_info.extension in self._exclude_extensions:
            return False

        return True

    def _should_exclude(self, path: str) -> bool:
        """检查路径是否应该排除"""
        path_lower = path.lower()
        for exclude in self._exclude_paths:
            if exclude.lower() in path_lower:
                return True
        return False

    def read_file(
        self,
        path: str,
        offset: int = 0,
        size: Optional[int] = None
    ) -> bytes:
        """
        读取文件内容

        Args:
            path: 文件路径
            offset: 读取偏移量
            size: 读取大小 (None=全部)

        Returns:
            bytes: 文件内容
        """
        with open(path, 'rb') as f:
            if offset > 0:
                f.seek(offset)
            if size is None:
                return f.read()
            return f.read(size)

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
            str: 哈希值 (十六进制)
        """
        if algorithm == "md5":
            hasher = __import__('hashlib').md5()
        elif algorithm == "sha1":
            hasher = __import__('hashlib').sha1()
        elif algorithm == "sha256":
            hasher = __import__('hashlib').sha256()
        else:
            hasher = __import__('hashlib').sha256()

        with open(path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)

        return hasher.hexdigest()

    # ==================== 辅助方法 ====================

    def get_mount_points(self) -> List[str]:
        """获取配置的挂载点列表"""
        return self._mount_points.copy()

    def get_excluded_paths(self) -> List[str]:
        """获取排除路径列表"""
        return self._exclude_paths.copy()

    def is_path_excluded(self, path: str) -> bool:
        """检查路径是否被排除"""
        return self._should_exclude(path)
