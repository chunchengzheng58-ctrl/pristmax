"""
RAID Adapter

RAID 阵列适配器，支持主流 RAID 卡 (MegaRAID, LSI, 硬件 RAID)
"""
import os
import re
import subprocess
from typing import Iterator, Optional, List, Dict

from storage.base import (
    StorageType, StorageInfo, FileInfo, ScanProgress,
    StorageAdapter
)


class RAIDAdapter(StorageAdapter):
    """
    RAID 阵列适配器

    支持主流 RAID 卡和硬件 RAID 阵列的扫描和管理

    Features:
    - MegaRAID (LSI) 支持
    - 硬件 RAID 状态检测
    - 逻辑磁盘扫描

    Example:
        # MegaRAID 配置
        adapter = RAIDAdapter({
            'id': 'raid-001',
            'name': 'RAID 5 阵列',
            'raid_type': 'megaraid',
            'adapter_id': 0
        })

        # 硬件 RAID (直接扫描挂载点)
        adapter = RAIDAdapter({
            'id': 'raid-002',
            'name': '硬件 RAID',
            'raid_type': 'hardware',
            'mount_points': ['/dev/sda']  # 直接指定设备
        })
    """

    # RAID 类型
    RAID_TYPES = ['megaraid', 'lsi', 'hardware', 'intel', 'dell', 'hp']

    def __init__(self, config: dict):
        super().__init__(config)
        self.raid_type = config.get('raid_type', 'hardware').lower()
        self.adapter_id = config.get('adapter_id', 0)
        self.controller = config.get('controller')  # 如 /dev/sda 或物理路径

        # MegaRAID 相关
        self._storcli_path = config.get('storcli_path', 'storcli')
        self._perccli_path = config.get('perccli_path', 'perccli64')

        # 磁盘信息缓存
        self._logical_drives: List[Dict] = []
        self._physical_drives: List[Dict] = []

    @property
    def storage_type(self) -> StorageType:
        return StorageType.RAID

    def connect(self) -> bool:
        """连接到 RAID 阵列"""
        try:
            if self.raid_type == 'megaraid':
                return self._connect_megaraid()
            elif self.raid_type == 'hardware':
                return self._connect_hardware()
            else:
                # 通用硬件 RAID
                self._is_connected = True
                return True
        except Exception as e:
            print(f"[RAID] Connection failed: {e}")
            return False

    def _connect_megaraid(self) -> bool:
        """连接 MegaRAID"""
        try:
            # 检查 storcli 或 perccli 是否可用
            cli_path = self._find_cli_tool()
            if not cli_path:
                print("[RAID] No RAID CLI tool found")
                return False

            # 获取 RAID 信息
            result = self._run_cli(cli_path, f'/c{self.adapter_id}/vall show')
            if result['returncode'] != 0:
                print(f"[RAID] CLI command failed: {result['stderr']}")
                return False

            # 解析输出
            self._parse_megaraid_info(result['stdout'])

            self._is_connected = True
            return True

        except Exception as e:
            print(f"[RAID] MegaRAID connection error: {e}")
            return False

    def _connect_hardware(self) -> bool:
        """连接硬件 RAID (直接访问挂载点)"""
        # 硬件 RAID 通常直接映射到系统磁盘
        self._is_connected = True
        return True

    def _find_cli_tool(self) -> Optional[str]:
        """查找可用的 RAID CLI 工具"""
        tools = [self._storcli_path, self._perccli_path, 'storcli', 'storcli64', 'perccli64', 'perccli']

        for tool in tools:
            try:
                result = subprocess.run(
                    [tool, '/help'],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode in [0, 1]:  # help 通常返回 1
                    return tool
            except:
                continue

        return None

    def _run_cli(self, tool: str, args: str) -> Dict:
        """运行 RAID CLI 命令"""
        try:
            cmd = f"{tool} {args}"
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        except Exception as e:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': str(e)
            }

    def _parse_megaraid_info(self, output: str):
        """解析 MegaRAID storcli 输出"""
        self._logical_drives = []
        self._physical_drives = []

        lines = output.split('\n')

        # 解析逻辑驱动器 (Virtual Drives)
        for line in lines:
            if 'VD' in line and 'type' not in line.lower():
                # 格式: VD 0 - OK, RAID 5, 1.817 TB
                match = re.search(r'VD\s+(\d+).*?(RAID[\s\w]*?),\s+([\d.]+\s*\w+)', line)
                if match:
                    self._logical_drives.append({
                        'id': match.group(1),
                        'type': match.group(2),
                        'size': match.group(3),
                    })

        # 解析物理驱动器 (Physical Drives)
        for line in lines:
            if 'PD' in line and 'drive' in line.lower():
                # 格式: PD: 0:0 - SATA, 500GB
                match = re.search(r'PD:\s+([\d:]+).*?,\s+([\d.]+\s*\w+)', line)
                if match:
                    self._physical_drives.append({
                        'id': match.group(1),
                        'size': match.group(2),
                    })

    def disconnect(self):
        """断开 RAID 连接"""
        self._logical_drives.clear()
        self._physical_drives.clear()
        self._is_connected = False

    def get_info(self) -> StorageInfo:
        """获取 RAID 阵列信息"""
        if not self._is_connected:
            return StorageInfo(
                name=self._storage_name or "RAID 阵列",
                storage_type=StorageType.RAID,
                path="",
                status="offline",
            )

        try:
            if self.raid_type == 'megaraid':
                return self._get_megaraid_info()
            else:
                # 使用系统磁盘信息
                return self._get_hardware_raid_info()

        except Exception as e:
            return StorageInfo(
                name=self._storage_name or "RAID 阵列",
                storage_type=StorageType.RAID,
                status="error",
                metadata={'error': str(e)}
            )

    def _get_megaraid_info(self) -> StorageInfo:
        """获取 MegaRAID 信息"""
        total_size = 0
        for vd in self._logical_drives:
            # 解析大小 (如 "1.817 TB")
            size_str = vd.get('size', '0 TB')
            match = re.search(r'([\d.]+)\s*(\w+)', size_str)
            if match:
                size_val = float(match.group(1))
                size_unit = match.group(2).upper()
                if size_unit == 'TB':
                    total_size += int(size_val * 1024 * 1024 * 1024 * 1024)
                elif size_unit == 'GB':
                    total_size += int(size_val * 1024 * 1024 * 1024)

        return StorageInfo(
            name=self._storage_name or f"MegaRAID Adapter {self.adapter_id}",
            storage_type=StorageType.RAID,
            path=f"/dev/megaraid{self.adapter_id}",
            total_size=total_size,
            used_size=0,  # RAID 不易确定
            free_size=0,
            is_mounted=True,
            status="healthy" if self._logical_drives else "degraded",
            metadata={
                'raid_type': self.raid_type,
                'adapter_id': self.adapter_id,
                'logical_drives': len(self._logical_drives),
                'physical_drives': len(self._physical_drives),
                'virtual_drives': [vd['type'] for vd in self._logical_drives],
            }
        )

    def _get_hardware_raid_info(self) -> StorageInfo:
        """获取硬件 RAID 信息"""
        # 硬件 RAID 通常映射到 /dev/sda 等设备
        device = self.controller or '/dev/sda'

        try:
            import shutil
            usage = shutil.disk_usage(device)
            return StorageInfo(
                name=self._storage_name or f"硬件 RAID ({device})",
                storage_type=StorageType.RAID,
                path=device,
                total_size=usage.total,
                used_size=usage.used,
                free_size=usage.free,
                is_mounted=True,
                status="healthy",
                metadata={
                    'raid_type': self.raid_type,
                    'device': device,
                }
            )
        except:
            return StorageInfo(
                name=self._storage_name or f"硬件 RAID ({device})",
                storage_type=StorageType.RAID,
                path=device,
                status="unknown",
            )

    def scan(
        self,
        path: str = "/",
        recursive: bool = True,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """
        扫描 RAID 阵列上的文件系统

        注意: RAID 适配器主要是提供阵列级别的信息，
        实际文件扫描由底层的逻辑卷/文件系统处理
        """
        # RAID 适配器本身不直接扫描文件
        # 而是委托给底层的逻辑磁盘适配器
        # 这里可以扫描 RAID 设备的分区表

        device = self.controller or '/dev/sda'

        if os.name == 'nt':
            # Windows: 扫描磁盘分区
            yield from self._scan_windows_disk(device)
        else:
            # Unix/Linux: 扫描块设备
            yield from self._scan_unix_device(device)

    def _scan_windows_disk(self, device: str) -> Iterator[FileInfo]:
        """扫描 Windows 磁盘"""
        try:
            import subprocess

            # 使用 wmic 获取磁盘分区信息
            result = subprocess.run(
                ['wmic', 'partition', 'get', 'DeviceID,Size,Type,Bootable', '/format:csv'],
                capture_output=True, text=True
            )

            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:  # 跳过标题
                parts = line.strip().split(',')
                if len(parts) >= 4:
                    device_id = parts[1].strip()
                    size = parts[2].strip()
                    part_type = parts[3].strip()

                    yield FileInfo(
                        path=device_id,
                        relative_path=device_id,
                        size=int(size) if size.isdigit() else 0,
                        modified_time=0,
                        storage_type=StorageType.RAID,
                        is_directory=False,
                        extension='',
                    )

        except Exception as e:
            print(f"[RAID] Windows disk scan error: {e}")

    def _scan_unix_device(self, device: str) -> Iterator[FileInfo]:
        """扫描 Unix/Linux 块设备"""
        try:
            # 列出所有分区
            partitions_path = f'/proc/partitions'
            if os.path.exists(partitions_path):
                with open(partitions_path, 'r') as f:
                    lines = f.readlines()

                for line in lines[2:]:  # 跳过标题
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        device_name = parts[0]
                        # 检查是否属于主设备
                        if device_name.startswith(device.replace('/dev/', '')):
                            partition = f'/dev/{device_name}'

                            yield FileInfo(
                                path=partition,
                                relative_path=partition,
                                size=int(parts[2]) * 1024,  # blocks to bytes
                                modified_time=0,
                                storage_type=StorageType.RAID,
                                is_directory=False,
                                extension='',
                            )

        except Exception as e:
            print(f"[RAID] Unix device scan error: {e}")

    def read_file(self, path: str, offset: int = 0, size: Optional[int] = None) -> bytes:
        """读取 RAID 设备文件 (不建议直接使用)"""
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
        hasher = __import__('hashlib')

        if algorithm == "md5":
            hasher = hasher.md5()
        elif algorithm == "sha1":
            hasher = hasher.sha1()
        else:
            hasher = hasher.sha256()

        with open(path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)

        return hasher.hexdigest()

    def get_physical_drives(self) -> List[Dict]:
        """获取物理驱动器信息"""
        return self._physical_drives.copy()

    def get_logical_drives(self) -> List[Dict]:
        """获取逻辑驱动器信息"""
        return self._logical_drives.copy()

    def get_array_status(self) -> Dict:
        """获取 RAID 阵列状态"""
        return {
            'raid_type': self.raid_type,
            'adapter_id': self.adapter_id,
            'physical_drives': len(self._physical_drives),
            'logical_drives': len(self._logical_drives),
            'is_healthy': len(self._logical_drives) > 0,
        }
