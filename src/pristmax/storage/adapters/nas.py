"""
NAS Adapter

NAS 存储适配器，支持 SMB/CIFS 和 NFS 协议
"""
import os
import time
from pathlib import Path
from typing import Iterator, Optional, List
import shutil

from storage.base import (
    StorageType, StorageInfo, FileInfo, ScanProgress,
    StorageAdapter
)


class NASAdapter(StorageAdapter):
    """
    NAS 存储适配器

    支持 SMB/CIFS (Windows 网络共享) 和 NFS (Unix 网络共享) 协议

    Features:
    - SMB/NFS 协议支持
    - 自动挂载/卸载
    - 凭据管理
    - 断线重连

    Example:
        # SMB 配置
        adapter = NASAdapter({
            'id': 'nas-001',
            'name': '群晖 NAS',
            'protocol': 'smb',
            'host': '192.168.1.100',
            'share': 'shared',
            'username': 'admin',
            'password': 'password'
        })

        # NFS 配置
        adapter = NASAdapter({
            'id': 'nas-002',
            'name': 'NFS 存储',
            'protocol': 'nfs',
            'host': '192.168.1.101',
            'share': '/volume1/shared'
        })
    """

    # Windows SMB 临时挂载点前缀
    WINDOWS_MOUNT_PREFIX = "Z:"

    def __init__(self, config: dict):
        super().__init__(config)
        self.protocol = config.get('protocol', 'smb').lower()  # smb | nfs
        self.host = config.get('host', '')
        self.share = config.get('share', '')
        self.username = config.get('username', 'guest')
        self.password = config.get('password', '')
        self.domain = config.get('domain', 'WORKGROUP')

        # 挂载相关
        self._mount_path: Optional[str] = None
        self._is_mounted = False

        # 初始化挂载路径
        self._init_mount_path()

    def _init_mount_path(self):
        """初始化挂载路径"""
        if os.name == 'nt':
            # Windows: 使用未占用的驱动器字母
            import string
            used = set()
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    used.add(letter)

            # 优先使用 Z:
            for letter in ['Z', 'Y', 'X', 'W', 'V']:
                if letter not in used:
                    self._mount_path = f"{letter}:\\"
                    break
        else:
            # Unix: 使用 /mnt 或 /media
            base = "/mnt" if os.path.exists("/mnt") else "/media"
            mount_name = f"{self.host.replace('.', '_')}_{self.share.replace('/', '_')}"
            legacy = f"{base}/pristine_{mount_name}"
            self._mount_path = legacy if os.path.ismount(legacy) else f"{base}/pristmax_{mount_name}"

    @property
    def storage_type(self) -> StorageType:
        return StorageType.NAS

    def connect(self) -> bool:
        """连接到 NAS"""
        if self._is_mounted and os.path.exists(self._mount_path):
            return True

        try:
            if self.protocol == 'smb':
                return self._mount_smb()
            elif self.protocol == 'nfs':
                return self._mount_nfs()
            else:
                print(f"[NAS] Unknown protocol: {self.protocol}")
                return False
        except Exception as e:
            print(f"[NAS] Connection failed: {e}")
            return False

    def _mount_smb(self) -> bool:
        """挂载 SMB 共享"""
        if os.name == 'nt':
            return self._mount_smb_windows()
        else:
            return self._mount_smb_unix()

    def _mount_smb_windows(self) -> bool:
        """Windows SMB 挂载"""
        if not self._mount_path:
            return False

        unc_path = f"\\\\{self.host}\\{self.share}"

        # 检查是否已挂载
        if os.path.exists(self._mount_path):
            self._is_mounted = True
            return True

        # 创建目录
        os.makedirs(self._mount_path, exist_ok=True)

        try:
            # 使用 net use 命令挂载
            import subprocess

            if self.password:
                cmd = ['net', 'use', self._mount_path, f'\\\\{self.host}\\{self.share}',
                       self.password, f'/USER:{self.username}']
            else:
                cmd = ['net', 'use', self._mount_path, f'\\\\{self.host}\\{self.share}']

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self._is_mounted = True
                print(f"[NAS] Mounted SMB: {unc_path} -> {self._mount_path}")
                return True
            else:
                print(f"[NAS] Mount failed: {result.stderr}")
                return False

        except Exception as e:
            print(f"[NAS] SMB mount error: {e}")
            return False

    def _mount_smb_unix(self) -> bool:
        """Unix SMB 挂载 (使用 CIFS 或 mount.cifs)"""
        try:
            import subprocess

            # 检查是否已挂载
            result = subprocess.run(['mount'], capture_output=True, text=True)
            if self._mount_path in result.stdout:
                self._is_mounted = True
                return True

            # 创建挂载点
            os.makedirs(self._mount_path, exist_ok=True)

            # 挂载命令
            cmd = [
                'mount', '-t', 'cifs',
                f'//{self.host}/{self.share}',
                self._mount_path,
                '-o', f'username={self.username},password={self.password}'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self._is_mounted = True
                return True
            else:
                print(f"[NAS] CIFS mount failed: {result.stderr}")
                return False

        except Exception as e:
            print(f"[NAS] CIFS mount error: {e}")
            return False

    def _mount_nfs(self) -> bool:
        """挂载 NFS 共享"""
        try:
            import subprocess

            # 检查是否已挂载
            result = subprocess.run(['mount'], capture_output=True, text=True)
            if self._mount_path in result.stdout:
                self._is_mounted = True
                return True

            # 创建挂载点
            os.makedirs(self._mount_path, exist_ok=True)

            # 挂载命令
            cmd = ['mount', '-t', 'nfs', f'{self.host}:{self.share}', self._mount_path]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self._is_mounted = True
                print(f"[NAS] Mounted NFS: {self.host}:{self.share} -> {self._mount_path}")
                return True
            else:
                print(f"[NAS] NFS mount failed: {result.stderr}")
                return False

        except Exception as e:
            print(f"[NAS] NFS mount error: {e}")
            return False

    def disconnect(self):
        """断开 NAS 连接"""
        if not self._is_mounted:
            return

        try:
            if self.protocol == 'nfs':
                cmd = ['umount', self._mount_path]
            else:
                if os.name == 'nt':
                    cmd = ['net', 'use', self._mount_path, '/delete', '/y']
                else:
                    cmd = ['umount', '-t', 'cifs', self._mount_path]

            import subprocess
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 or 'not found' in result.stderr.lower():
                self._is_mounted = False
                print(f"[NAS] Unmounted: {self._mount_path}")

        except Exception as e:
            print(f"[NAS] Unmount error: {e}")

    def get_info(self) -> StorageInfo:
        """获取 NAS 存储信息"""
        if not self._is_mounted or not os.path.exists(self._mount_path):
            return StorageInfo(
                name=self._storage_name or f"NAS ({self.host})",
                storage_type=StorageType.NAS,
                path=f"//{self.host}/{self.share}",
                status="offline",
            )

        try:
            usage = shutil.disk_usage(self._mount_path)

            return StorageInfo(
                name=self._storage_name or f"NAS ({self.host})",
                storage_type=StorageType.NAS,
                path=self._mount_path,
                total_size=usage.total,
                used_size=usage.used,
                free_size=usage.free,
                is_mounted=True,
                status="healthy",
                metadata={
                    'host': self.host,
                    'share': self.share,
                    'protocol': self.protocol,
                }
            )
        except Exception as e:
            return StorageInfo(
                name=self._storage_name or f"NAS ({self.host})",
                storage_type=StorageType.NAS,
                path=f"//{self.host}/{self.share}",
                status="error",
                metadata={'error': str(e)}
            )

    def scan(
        self,
        path: str = "/",
        recursive: bool = True,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """扫描 NAS 路径"""
        if not self._is_mounted:
            if not self.connect():
                return

        scan_path = self._mount_path
        if path != "/":
            scan_path = os.path.join(self._mount_path, path.lstrip('/'))

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
                storage_type=StorageType.NAS,
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
        if not path.startswith(self._mount_path):
            path = os.path.join(self._mount_path, path.lstrip('/'))

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
        if not path.startswith(self._mount_path):
            path = os.path.join(self._mount_path, path.lstrip('/'))

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

    @property
    def mount_path(self) -> Optional[str]:
        """获取挂载路径"""
        return self._mount_path

    @property
    def is_mounted(self) -> bool:
        """是否已挂载"""
        return self._is_mounted
