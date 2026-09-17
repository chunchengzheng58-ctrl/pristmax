"""
USB Adapter

USB/外置存储适配器，支持 USB 硬盘、U 盘等可移动存储设备
"""
import os
import shutil
import psutil
from pathlib import Path
from typing import Iterator, Optional, List

from storage.base import (
    StorageType, StorageInfo, FileInfo, ScanProgress,
    StorageAdapter
)


class USBAdapter(StorageAdapter):
    """
    USB/外置存储适配器

    支持 USB 硬盘、U 盘等可移动存储设备的自动发现和扫描

    Features:
    - 自动发现已连接的 USB 设备
    - 热插拔检测
    - 多设备管理

    Example:
        adapter = USBAdapter({
            'id': 'usb-001',
            'name': '外置硬盘',
            'auto_detect': True
        })

        # 自动发现所有 USB 设备
        devices = adapter.discover_devices()
        for device in devices:
            print(f"{device.name}: {device.path}")
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.auto_detect = config.get('auto_detect', True)
        self.device_id = config.get('device_id')  # 可指定特定设备
        self._current_device: Optional[StorageInfo] = None

    @property
    def storage_type(self) -> StorageType:
        return StorageType.USB

    def connect(self) -> bool:
        """连接 USB 设备"""
        if self.auto_detect:
            # 自动发现并连接第一个可用设备
            devices = self.discover_devices()
            if devices:
                self._current_device = devices[0]
                self._is_connected = True
                return True
            return False

        if self.device_id:
            # 连接指定设备
            return self._connect_by_id(self.device_id)

        self._is_connected = True
        return True

    def _connect_by_id(self, device_id: str) -> bool:
        """通过设备 ID 连接"""
        for partition in psutil.disk_partitions():
            if partition.device == device_id or device_id in partition.opts:
                self._current_device = self._create_device_info(partition)
                self._is_connected = True
                return True
        return False

    def disconnect(self):
        """断开 USB 设备"""
        self._current_device = None
        self._is_connected = False

    def discover_devices(self) -> List[StorageInfo]:
        """
        自动发现已连接的 USB/外置设备

        Returns:
            List[StorageInfo]: 设备信息列表
        """
        devices = []

        for partition in psutil.disk_partitions():
            # 检查是否为可移动/外置设备
            if self._is_removable(partition):
                device_info = self._create_device_info(partition)
                devices.append(device_info)

        return devices

    def _is_removable(self, partition) -> bool:
        """检查是否为可移动设备"""
        # Windows
        if os.name == 'nt':
            # 检查是否为可移动媒体或 USB
            if 'removable' in partition.opts.lower():
                return True
            # 检查设备类型
            try:
                import subprocess
                result = subprocess.run(
                    ['wmic', 'diskdrive', 'get', 'model,interfacetype', '/format:csv'],
                    capture_output=True, text=True
                )
                if 'USB' in result.stdout or 'Removable' in result.stdout:
                    return True
            except:
                pass

        # Unix/Linux
        else:
            # 检查是否为 USB 总线
            if '/dev/sd' in partition.device and partition.mountpoint:
                # 检查 /sys/block 中是否为 USB
                device_name = os.path.basename(partition.device)
                sys_path = f"/sys/block/{device_name}"
                if os.path.exists(sys_path):
                    # 检查是否为 USB
                    usb_path = f"{sys_path}/device"
                    if os.path.exists(usb_path):
                        return True

        return False

    def _create_device_info(self, partition) -> StorageInfo:
        """创建设备信息"""
        try:
            usage = shutil.disk_usage(partition.mountpoint)
            return StorageInfo(
                name=self._storage_name or f"USB 设备 ({partition.device})",
                storage_type=StorageType.USB,
                path=partition.mountpoint,
                total_size=usage.total,
                used_size=usage.used,
                free_size=usage.free,
                is_mounted=True,
                status="healthy",
                metadata={
                    'device': partition.device,
                    'fstype': partition.fstype,
                    'opts': partition.opts,
                }
            )
        except Exception as e:
            return StorageInfo(
                name=self._storage_name or f"USB 设备 ({partition.device})",
                storage_type=StorageType.USB,
                path=partition.mountpoint or partition.device,
                status="error",
                metadata={'error': str(e)}
            )

    def get_info(self) -> StorageInfo:
        """获取 USB 设备信息"""
        if self._current_device:
            return self._current_device

        if self.auto_detect:
            devices = self.discover_devices()
            if devices:
                return devices[0]

        return StorageInfo(
            name=self._storage_name or "USB 存储",
            storage_type=StorageType.USB,
            path="",
            status="offline",
        )

    def scan(
        self,
        path: str = "/",
        recursive: bool = True,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """扫描 USB 设备"""
        device_info = self.get_info()
        if not device_info.is_mounted or not device_info.path:
            return

        scan_path = device_info.path if path == "/" else path

        if not os.path.exists(scan_path):
            return

        yield from self._scan_directory(scan_path, scan_path, recursive, progress_callback)

    def _scan_directory(
        self,
        root_path: str,
        current_path: str,
        recursive: bool,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """递归扫描目录"""
        try:
            for entry in os.scandir(current_path):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if recursive:
                            yield from self._scan_directory(
                                root_path, entry.path, recursive, progress_callback
                            )
                    elif entry.is_file(follow_symlinks=False):
                        file_info = self._create_file_info(entry.path, root_path)
                        if file_info:
                            yield file_info

                except (PermissionError, OSError):
                    continue

        except (PermissionError, OSError):
            pass

    def _create_file_info(self, file_path: str, root_path: str) -> Optional[FileInfo]:
        """创建文件信息对象"""
        try:
            stat = os.stat(file_path, follow_symlinks=False)

            try:
                relative_path = os.path.relpath(file_path, root_path)
            except ValueError:
                relative_path = file_path

            return FileInfo(
                path=file_path,
                relative_path=relative_path,
                size=stat.st_size,
                modified_time=stat.st_mtime,
                storage_type=StorageType.USB,
                is_directory=False,
                extension=self._get_file_extension(file_path),
            )
        except (PermissionError, OSError, FileNotFoundError):
            return None

    def read_file(
        self,
        path: str,
        offset: int = 0,
        size: Optional[int] = None
    ) -> bytes:
        """读取文件"""
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
        """计算文件哈希"""
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

    def eject(self) -> bool:
        """
        弹出 USB 设备

        Returns:
            bool: 是否成功弹出
        """
        device_info = self.get_info()
        if not device_info.is_mounted:
            return True

        try:
            if os.name == 'nt':
                # Windows: 使用 mountvol 或 eject
                import subprocess
                result = subprocess.run(
                    ['mountvol', device_info.path, '/P'],
                    capture_output=True, text=True
                )
                return result.returncode == 0
            else:
                # Unix: 使用 umount
                import subprocess
                result = subprocess.run(
                    ['umount', device_info.path],
                    capture_output=True, text=True
                )
                return result.returncode == 0

        except Exception as e:
            print(f"[USB] Eject failed: {e}")
            return False

    def get_current_device(self) -> Optional[StorageInfo]:
        """获取当前设备信息"""
        return self._current_device
