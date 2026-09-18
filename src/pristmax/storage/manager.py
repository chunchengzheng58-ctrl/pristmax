"""
Storage Manager

统一存储管理器，负责管理所有存储适配器实例
"""
import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Iterator, Callable
from dataclasses import asdict

from storage.base import StorageType, StorageInfo, FileInfo, ScanProgress, StorageAdapter
from storage.registry import StorageRegistry


class ScanTask:
    """扫描任务"""

    def __init__(self, task_id: str, storage_id: str, adapter: StorageAdapter):
        self.task_id = task_id
        self.storage_id = storage_id
        self.adapter = adapter
        self.status = "pending"  # pending/running/completed/failed
        self.progress = ScanProgress()
        self.files: List[FileInfo] = []
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.completed_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            'task_id': self.task_id,
            'storage_id': self.storage_id,
            'status': self.status,
            'progress': self.progress.to_dict(),
            'files_count': len(self.files),
            'error': self.error,
            'created_at': self.created_at,
            'completed_at': self.completed_at,
        }


class StorageManager:
    """
    存储管理器

    统一管理所有存储适配器实例，提供存储注册、扫描、查询等功能

    Example:
        manager = StorageManager()

        # 添加存储
        manager.add_storage('local_disk', {
            'id': 'disk-c',
            'name': '本地磁盘 C:',
            'mount_points': ['C:\\']
        })

        # 列出所有存储
        storages = manager.list_storages()

        # 扫描存储
        files = list(manager.scan_storage('disk-c'))

        # 跨存储去重分析
        duplicates = manager.find_duplicates(['disk-c', 'disk-d'])
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        """初始化管理器"""
        if self._initialized:
            return

        self._adapters: Dict[str, StorageAdapter] = {}
        self._scan_tasks: Dict[str, ScanTask] = {}
        self._task_counter = 0
        self._registry = StorageRegistry()
        self._config_path = Path(__file__).parent.parent / "config" / "storages.json"
        self._initialized = True

        # 确保配置目录存在
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        # 加载已保存的配置
        self._load_config()

        # 如果没有存储配置，自动检测本地磁盘
        if not self._adapters:
            self._auto_detect_storages()
        else:
            print(f"[Manager] Using {len(self._adapters)} storages from config")

    def _generate_task_id(self) -> str:
        """生成唯一任务 ID"""
        self._task_counter += 1
        return f"scan-{int(time.time() * 1000)}-{self._task_counter}"

    # ==================== 存储管理 ====================

    def add_storage(self, storage_type: str, config: dict) -> Optional[str]:
        """
        添加存储

        Args:
            storage_type: 存储类型 (local_disk/nas/usb/cloud/raid)
            config: 配置信息

        Returns:
            str: 存储 ID，失败返回 None
        """
        # 转换类型字符串到枚举
        try:
            st = StorageType(storage_type)
        except ValueError:
            print(f"[Manager] Unknown storage type: {storage_type}")
            return None

        # 创建适配器
        adapter = self._registry.create(st, config)
        if adapter is None:
            print(f"[Manager] Failed to create adapter for {storage_type}")
            return None

        # 分配默认 ID
        if 'id' not in config:
            config['id'] = f"{storage_type}-{int(time.time())}"

        storage_id = config['id']

        # 连接存储
        try:
            if not adapter.connect():
                print(f"[Manager] Failed to connect storage {storage_id}")
                return None
        except Exception as e:
            print(f"[Manager] Connection error: {e}")
            return None

        # 注册适配器
        self._adapters[storage_id] = adapter
        print(f"[Manager] Added storage: {storage_id} ({storage_type})")

        # 保存配置
        self._save_config()

        return storage_id

    def remove_storage(self, storage_id: str) -> bool:
        """
        移除存储

        Args:
            storage_id: 存储 ID

        Returns:
            bool: 是否成功移除
        """
        if storage_id not in self._adapters:
            return False

        adapter = self._adapters[storage_id]
        adapter.disconnect()
        del self._adapters[storage_id]

        print(f"[Manager] Removed storage: {storage_id}")
        self._save_config()
        return True

    def get_storage(self, storage_id: str) -> Optional[StorageAdapter]:
        """
        获取存储适配器

        Args:
            storage_id: 存储 ID

        Returns:
            存储适配器，未找到返回 None
        """
        return self._adapters.get(storage_id)

    def list_storages(self) -> List[dict]:
        """
        列出所有存储

        Returns:
            存储信息列表
        """
        result = []
        for storage_id, adapter in self._adapters.items():
            try:
                info = adapter.get_info()
                result.append(info.to_dict())
            except Exception as e:
                # 存储可能已离线
                result.append({
                    'id': storage_id,
                    'name': adapter.storage_name or storage_id,
                    'type': adapter.storage_type.value,
                    'status': 'error',
                    'error': str(e),
                })
        return result

    # ==================== 扫描功能 ====================

    def scan_storage(
        self,
        storage_id: str,
        path: str = "/",
        recursive: bool = True,
        progress_callback: Optional[Callable[[ScanProgress], None]] = None
    ) -> Iterator[FileInfo]:
        """
        扫描存储

        Args:
            storage_id: 存储 ID
            path: 扫描路径
            recursive: 是否递归
            progress_callback: 进度回调

        Yields:
            FileInfo: 文件信息
        """
        adapter = self._adapters.get(storage_id)
        if adapter is None:
            print(f"[Manager] Storage not found: {storage_id}")
            return

        if not adapter.is_connected():
            if not adapter.connect():
                print(f"[Manager] Failed to connect: {storage_id}")
                return

        yield from adapter.scan(path, recursive, progress_callback)

    def start_scan_task(
        self,
        storage_id: str,
        path: str = "/",
        recursive: bool = True
    ) -> Optional[str]:
        """
        启动后台扫描任务

        Args:
            storage_id: 存储 ID
            path: 扫描路径
            recursive: 是否递归

        Returns:
            str: 任务 ID
        """
        adapter = self._adapters.get(storage_id)
        if adapter is None:
            return None

        task_id = self._generate_task_id()
        task = ScanTask(task_id, storage_id, adapter)
        self._scan_tasks[task_id] = task

        # 后台运行扫描
        def _run_scan():
            task.status = "running"
            task.progress.start_time = time.time()

            def progress_callback(progress: ScanProgress):
                task.progress = progress

            try:
                for file_info in adapter.scan(path, recursive, progress_callback):
                    task.files.append(file_info)
                    task.progress.current += 1
                    task.progress.bytes_scanned += file_info.size
                    task.progress.current_path = file_info.path

            except Exception as e:
                task.error = str(e)
                task.status = "failed"
                print(f"[Manager] Scan task {task_id} failed: {e}")

            task.status = "completed"
            task.completed_at = time.time()

        thread = threading.Thread(target=_run_scan, daemon=True)
        thread.start()

        return task_id

    def get_scan_task(self, task_id: str) -> Optional[dict]:
        """
        获取扫描任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务信息字典
        """
        task = self._scan_tasks.get(task_id)
        if task is None:
            return None
        return task.to_dict()

    def get_scan_results(self, task_id: str) -> Optional[List[dict]]:
        """
        获取扫描结果

        Args:
            task_id: 任务 ID

        Returns:
            文件信息列表
        """
        task = self._scan_tasks.get(task_id)
        if task is None:
            return None
        return [f.to_dict() for f in task.files]

    # ==================== 去重分析 ====================

    def find_duplicates(
        self,
        storage_ids: List[str],
        min_size: int = 1024  # 最小 1KB
    ) -> Dict[str, List[FileInfo]]:
        """
        跨存储查找重复文件

        Args:
            storage_ids: 要扫描的存储 ID 列表
            min_size: 最小文件大小 (bytes)

        Returns:
            Dict[str, List[FileInfo]]: 按哈希分组的重复文件
            key: 文件哈希
            value: 具有相同哈希的文件列表
        """
        hash_map: Dict[str, List[FileInfo]] = {}
        processed = 0

        for storage_id in storage_ids:
            adapter = self._adapters.get(storage_id)
            if adapter is None:
                continue

            for file_info in adapter.scan():
                if file_info.is_directory:
                    continue
                if file_info.size < min_size:
                    continue

                # 计算哈希 (如果尚未计算)
                if file_info.hash is None:
                    try:
                        file_info.hash = adapter.compute_hash(file_info.path)
                    except Exception:
                        continue

                # 存储到哈希表
                if file_info.hash not in hash_map:
                    hash_map[file_info.hash] = []

                hash_map[file_info.hash].append(file_info)
                processed += 1

        # 返回有重复的文件
        duplicates = {h: files for h, files in hash_map.items() if len(files) > 1}

        print(f"[Manager] Scanned {processed} files, found {len(duplicates)} duplicate groups")
        return duplicates

    # ==================== 配置管理 ====================

    def _get_config_path(self) -> Path:
        """获取配置文件路径"""
        return self._config_path

    def _load_config(self):
        """从文件加载配置"""
        if not self._config_path.exists():
            return

        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            storages = config.get('storages', [])
            for storage_config in storages:
                storage_type = storage_config.get('type')
                if storage_type and storage_config.get('enabled', True):
                    self.add_storage(storage_type, storage_config)

            print(f"[Manager] Loaded {len(storages)} storage configurations")

        except Exception as e:
            print(f"[Manager] Failed to load config: {e}")

    def _auto_detect_storages(self):
        """自动检测并添加本地存储（跳过已存在的 ID）"""
        import os, shutil

        if os.name == 'nt':
            # Windows: 检测所有可用驱动器
            for letter in range(ord('C'), ord('Z') + 1):
                drive = f"{chr(letter)}:\\"
                storage_id = f'local-{letter}'
                # 跳过已存在的
                if storage_id in self._adapters:
                    continue
                try:
                    if os.path.exists(drive):
                        usage = shutil.disk_usage(drive)
                        sid = self.add_storage('local_disk', {
                            'id': storage_id,
                            'name': f'本地磁盘 ({chr(letter)}:)',
                            'mount_points': [drive],
                            'enabled': True
                        })
                        if sid:
                            print(f"[Manager] Auto-detected {drive} ({usage.total / 1024**3:.0f} GB)")
                except Exception:
                    pass
        else:
            # Unix: 根目录
            storage_id = 'local-root'
            if storage_id in self._adapters:
                return
            try:
                usage = shutil.disk_usage('/')
                sid = self.add_storage('local_disk', {
                    'id': storage_id,
                    'name': '根目录 (/)',
                    'mount_points': ['/'],
                    'enabled': True
                })
                if sid:
                    print(f"[Manager] Auto-detected / ({usage.total / 1024**3:.0f} GB)")
            except Exception:
                pass
        """自动检测并添加本地存储"""
        import os, shutil

        if os.name == 'nt':
            # Windows: 检测所有可用驱动器
            for letter in range(ord('C'), ord('Z') + 1):
                drive = f"{chr(letter)}:\\"
                try:
                    if os.path.exists(drive):
                        usage = shutil.disk_usage(drive)
                        storage_id = self.add_storage('local_disk', {
                            'id': f'local-{letter}',
                            'name': f'本地磁盘 ({chr(letter)}:)',
                            'mount_points': [drive],
                            'enabled': True
                        })
                        if storage_id:
                            print(f"[Manager] Auto-detected {drive} ({usage.total / 1024**3:.0f} GB)")
                except Exception:
                    pass
        else:
            # Unix: 根目录
            try:
                usage = shutil.disk_usage('/')
                storage_id = self.add_storage('local_disk', {
                    'id': 'local-root',
                    'name': '根目录 (/)',
                    'mount_points': ['/'],
                    'enabled': True
                })
                if storage_id:
                    print(f"[Manager] Auto-detected / ({usage.total / 1024**3:.0f} GB)")
            except Exception:
                pass

    def _save_config(self):
        """保存配置到文件"""
        storages = []
        for storage_id, adapter in self._adapters.items():
            config = adapter.config.copy()
            config['type'] = adapter.storage_type.value
            storages.append(config)

        config = {'storages': storages}

        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Manager] Failed to save config: {e}")

    # ==================== 工具方法 ====================

    def get_storage_types(self) -> List[str]:
        """获取支持的存储类型列表"""
        return [t.value for t in self._registry.list_registered()]

    def refresh_storage(self, storage_id: str) -> bool:
        """
        刷新存储信息

        Args:
            storage_id: 存储 ID

        Returns:
            bool: 是否成功
        """
        adapter = self._adapters.get(storage_id)
        if adapter is None:
            return False

        try:
            adapter.disconnect()
            return adapter.connect()
        except Exception:
            return False

    def clear_all(self):
        """清空所有存储 (主要用于测试)"""
        for storage_id in list(self._adapters.keys()):
            self.remove_storage(storage_id)

    def __repr__(self) -> str:
        return f"<StorageManager storages={len(self._adapters)} tasks={len(self._scan_tasks)}>"


# 全局实例
storage_manager = StorageManager()
