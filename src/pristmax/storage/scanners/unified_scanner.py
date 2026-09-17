"""
Unified Scanner

统一扫描引擎，支持跨多种存储类型进行文件扫描和去重分析
"""
import threading
import time
from typing import Dict, List, Optional, Iterator, Callable
from collections import defaultdict

from storage.base import StorageType, FileInfo, ScanProgress, StorageAdapter


class DuplicateGroup:
    """重复文件组"""

    def __init__(self, file_hash: str):
        self.hash = file_hash
        self.files: List[FileInfo] = []
        self.total_size = 0
        self.wasted_size = 0

    def add_file(self, file_info: FileInfo):
        """添加文件到组"""
        self.files.append(file_info)
        self.total_size += file_info.size
        # 浪费空间 = (文件数 - 1) * 文件大小
        self.wasted_size = file_info.size * (len(self.files) - 1)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def original_size(self) -> int:
        """原始大小 (最大文件的大小)"""
        if not self.files:
            return 0
        return max(f.size for f in self.files)

    def to_dict(self) -> dict:
        return {
            'hash': self.hash,
            'file_count': self.file_count,
            'original_size': self.original_size,
            'total_size': self.total_size,
            'wasted_size': self.wasted_size,
            'savings_percent': round(self.wasted_size / self.total_size * 100, 1) if self.total_size > 0 else 0,
            'files': [f.to_dict() for f in self.files],
        }


class UnifiedScanner:
    """
    统一扫描器

    提供跨存储类型的统一文件扫描和重复文件检测功能

    Features:
    - 多存储并行扫描
    - 增量扫描支持
    - 重复文件检测
    - 扫描进度跟踪

    Example:
        scanner = UnifiedScanner()

        # 扫描多个存储
        scanner.add_storage('disk-c', local_adapter)
        scanner.add_storage('disk-d', local_adapter_2)

        # 启动扫描
        scanner.start_scan()

        # 监听进度
        while scanner.is_running:
            progress = scanner.get_progress()
            print(f"Scanned: {progress['scanned']} files")
            time.sleep(1)

        # 获取结果
        duplicates = scanner.get_duplicates()
        all_files = scanner.get_all_files()
    """

    def __init__(self):
        self._adapters: Dict[str, StorageAdapter] = {}
        self._all_files: List[FileInfo] = []
        self._duplicates: Dict[str, DuplicateGroup] = {}

        self._is_running = False
        self._is_cancelled = False
        self._progress = ScanProgress()
        self._lock = threading.Lock()

        self._scan_thread: Optional[threading.Thread] = None
        self._progress_callbacks: List[Callable[[ScanProgress], None]] = []

    def add_storage(self, storage_id: str, adapter: StorageAdapter):
        """
        添加存储到扫描器

        Args:
            storage_id: 存储 ID
            adapter: 存储适配器
        """
        with self._lock:
            self._adapters[storage_id] = adapter

    def remove_storage(self, storage_id: str):
        """
        从扫描器移除存储

        Args:
            storage_id: 存储 ID
        """
        with self._lock:
            if storage_id in self._adapters:
                del self._adapters[storage_id]

    def clear(self):
        """清空所有数据"""
        with self._lock:
            self._all_files.clear()
            self._duplicates.clear()
            self._progress = ScanProgress()

    def add_progress_callback(self, callback: Callable[[ScanProgress], None]):
        """添加进度回调"""
        self._progress_callbacks.append(callback)

    def start_scan(
        self,
        paths: Optional[Dict[str, str]] = None,
        recursive: bool = True,
        compute_hash: bool = True,
        min_file_size: int = 1024
    ):
        """
        启动扫描 (异步)

        Args:
            paths: 存储 ID -> 扫描路径 的映射
            recursive: 是否递归扫描
            compute_hash: 是否计算哈希
            min_file_size: 最小文件大小
        """
        if self._is_running:
            print("[Scanner] Already running")
            return

        self._is_running = True
        self._is_cancelled = False
        self._progress = ScanProgress()
        self._progress.start_time = time.time()

        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(paths, recursive, compute_hash, min_file_size),
            daemon=True
        )
        self._scan_thread.start()

    def _scan_worker(
        self,
        paths: Optional[Dict[str, str]],
        recursive: bool,
        compute_hash: bool,
        min_file_size: int
    ):
        """扫描工作线程"""
        hash_map: Dict[str, List[FileInfo]] = defaultdict(list)

        try:
            for storage_id, adapter in self._adapters.items():
                if self._is_cancelled:
                    break

                scan_path = paths.get(storage_id, "/") if paths else "/"

                for file_info in adapter.scan(scan_path, recursive):
                    if self._is_cancelled:
                        break

                    # 过滤小文件
                    if file_info.size < min_file_size:
                        continue

                    # 更新进度
                    self._progress.current += 1
                    self._progress.current_path = file_info.path
                    self._progress.bytes_scanned += file_info.size

                    # 计算哈希
                    if compute_hash:
                        try:
                            file_info.hash = adapter.compute_hash(file_info.path)
                        except Exception:
                            continue

                    # 存储文件
                    with self._lock:
                        self._all_files.append(file_info)

                        if file_info.hash:
                            hash_map[file_info.hash].append(file_info)

                    # 回调进度
                    self._notify_progress()

        except Exception as e:
            print(f"[Scanner] Error: {e}")

        finally:
            # 处理重复文件
            with self._lock:
                for file_hash, files in hash_map.items():
                    if len(files) > 1:
                        group = DuplicateGroup(file_hash)
                        for f in files:
                            group.add_file(f)
                        self._duplicates[file_hash] = group

            self._is_running = False
            self._progress.elapsed_seconds = time.time() - self._progress.start_time

    def cancel(self):
        """取消扫描"""
        self._is_cancelled = True

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._is_running

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        等待扫描完成

        Args:
            timeout: 超时时间 (秒)

        Returns:
            bool: 是否完成 (True) 或超时 (False)
        """
        if self._scan_thread:
            self._scan_thread.join(timeout)
            return not self._scan_thread.is_alive()
        return True

    def get_progress(self) -> dict:
        """获取扫描进度"""
        with self._lock:
            self._progress.elapsed_seconds = time.time() - self._progress.start_time
            return self._progress.to_dict()

    def get_all_files(self) -> List[dict]:
        """获取所有扫描到的文件"""
        with self._lock:
            return [f.to_dict() for f in self._all_files]

    def get_files_by_type(self, storage_type: StorageType) -> List[dict]:
        """获取指定类型的文件"""
        with self._lock:
            return [
                f.to_dict() for f in self._all_files
                if f.storage_type == storage_type
            ]

    def get_duplicates(self) -> List[dict]:
        """获取重复文件组"""
        with self._lock:
            return [g.to_dict() for g in self._duplicates.values()]

    def get_total_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            total_files = len(self._all_files)
            total_size = sum(f.size for f in self._all_files)

            duplicate_groups = len(self._duplicates)
            duplicate_files = sum(g.file_count for g in self._duplicates.values())
            duplicate_size = sum(g.wasted_size for g in self._duplicates.values())

            return {
                'total_files': total_files,
                'total_size': total_size,
                'duplicate_groups': duplicate_groups,
                'duplicate_files': duplicate_files,
                'duplicate_size': duplicate_size,
                'potential_savings': duplicate_size,
                'scan_elapsed': round(self._progress.elapsed_seconds, 1),
            }

    def _notify_progress(self):
        """通知进度更新"""
        if self._progress_callbacks:
            with self._lock:
                progress = self._progress.to_dict()
            for callback in self._progress_callbacks:
                try:
                    callback(ScanProgress(**progress))
                except Exception:
                    pass

    def __repr__(self) -> str:
        return f"<UnifiedScanner running={self._is_running} files={len(self._all_files)}>"


# 全局实例
unified_scanner = UnifiedScanner()
