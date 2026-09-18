"""
Storage Agent: 智能存储管家

功能：
- 大文件分析
- 重复文件检测
- 存储使用统计
- 文件分类整理
- 智能搜索
"""
import os
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class FileInfo:
    """文件信息"""
    path: str
    name: str
    size: int
    size_display: str
    extension: str
    modified: str
    created: str
    type_category: str

    @staticmethod
    def format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


@dataclass
class DuplicateGroup:
    """重复文件组"""
    hash: str
    size: int
    size_display: str
    count: int
    files: List[str]
    wasted_space: int


class StorageAgent:
    """
    智能存储管家 Agent

    核心功能：
    1. 大文件分析 - 找出占用空间最多的文件
    2. 重复文件检测 - 通过哈希检测重复文件
    3. 存储统计 - 各类型文件占用空间
    4. 文件分类 - 按类型自动分类
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS file_cache (
                path TEXT PRIMARY KEY,
                name TEXT,
                size INTEGER,
                hash TEXT,
                extension TEXT,
                category TEXT,
                modified TEXT,
                created TEXT,
                scanned_at TEXT
            )
        ''')
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_size ON file_cache(size DESC)
        ''')
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_hash ON file_cache(hash)
        ''')
        self.conn.commit()

    def analyze_large_files(
        self,
        root_path: str,
        min_size_mb: int = 100,
        limit: int = 20
    ) -> List[FileInfo]:
        """
        分析大文件

        Args:
            root_path: 扫描根目录
            min_size_mb: 最小文件大小(MB)
            limit: 返回数量

        Returns:
            大文件列表
        """
        min_size = min_size_mb * 1024 * 1024
        results = []

        for dirpath, dirnames, filenames in os.walk(root_path):
            # 跳过隐藏目录和系统目录
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]

            for filename in filenames:
                if filename.startswith('.'):
                    continue

                filepath = os.path.join(dirpath, filename)
                try:
                    size = os.path.getsize(filepath)
                    if size >= min_size:
                        stat = os.stat(filepath)
                        ext = Path(filename).suffix.lower()

                        results.append(FileInfo(
                            path=filepath,
                            name=filename,
                            size=size,
                            size_display=FileInfo.format_size(size),
                            extension=ext,
                            modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            created=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            type_category=self._categorize(ext)
                        ))
                except (OSError, PermissionError):
                    continue

        # 按大小排序
        results.sort(key=lambda x: x.size, reverse=True)
        return results[:limit]

    def find_duplicates(self, root_path: str, min_size_kb: int = 1) -> List[DuplicateGroup]:
        """
        查找重复文件

        Args:
            root_path: 扫描根目录
            min_size_kb: 最小文件大小(KB)

        Returns:
            重复文件组列表
        """
        min_size = min_size_kb * 1024
        hash_groups: Dict[str, List[str]] = {}
        size_groups: Dict[int, List[str]] = {}

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]

            for filename in filenames:
                if filename.startswith('.'):
                    continue

                filepath = os.path.join(dirpath, filename)
                try:
                    size = os.path.getsize(filepath)
                    if size < min_size:
                        continue

                    # 按大小分组
                    if size not in size_groups:
                        size_groups[size] = []
                    size_groups[size].append(filepath)

                except (OSError, PermissionError):
                    continue

        # 只对可能有重复的大小计算哈希
        for size, files in size_groups.items():
            if len(files) < 2:
                continue

            for filepath in files:
                file_hash = self._compute_hash(filepath)
                if file_hash:
                    if file_hash not in hash_groups:
                        hash_groups[file_hash] = []
                    hash_groups[file_hash].append(filepath)

        # 构建重复组
        duplicates = []
        for file_hash, files in hash_groups.items():
            if len(files) < 2:
                continue

            size = os.path.getsize(files[0])
            wasted = size * (len(files) - 1)

            duplicates.append(DuplicateGroup(
                hash=file_hash[:16],
                size=size,
                size_display=FileInfo.format_size(size),
                count=len(files),
                files=files,
                wasted_space=wasted
            ))

        # 按浪费空间排序
        duplicates.sort(key=lambda x: x.wasted_space, reverse=True)
        return duplicates

    def get_storage_stats(self, root_path: str) -> Dict:
        """
        获取存储统计

        Returns:
            统计信息
        """
        stats = {
            'total_files': 0,
            'total_size': 0,
            'total_size_display': '0 B',
            'by_category': {},
            'by_extension': {},
            'largest_dirs': []
        }

        dir_sizes: Dict[str, int] = {}

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            dir_size = 0

            for filename in filenames:
                if filename.startswith('.'):
                    continue

                filepath = os.path.join(dirpath, filename)
                try:
                    size = os.path.getsize(filepath)
                    stats['total_files'] += 1
                    stats['total_size'] += size
                    dir_size += size

                    ext = Path(filename).suffix.lower() or '.none'
                    category = self._categorize(ext)

                    # 按分类统计
                    if category not in stats['by_category']:
                        stats['by_category'][category] = {'count': 0, 'size': 0}
                    stats['by_category'][category]['count'] += 1
                    stats['by_category'][category]['size'] += size

                    # 按扩展名统计
                    if ext not in stats['by_extension']:
                        stats['by_extension'][ext] = {'count': 0, 'size': 0}
                    stats['by_extension'][ext]['count'] += 1
                    stats['by_extension'][ext]['size'] += size

                except (OSError, PermissionError):
                    continue

            # 目录大小
            if dir_size > 0:
                dir_sizes[dirpath] = dir_size

        stats['total_size_display'] = FileInfo.format_size(stats['total_size'])

        # 格式化大小
        for cat in stats['by_category']:
            stats['by_category'][cat]['size_display'] = FileInfo.format_size(
                stats['by_category'][cat]['size']
            )

        for ext in stats['by_extension']:
            stats['by_extension'][ext]['size_display'] = FileInfo.format_size(
                stats['by_extension'][ext]['size']
            )

        # 最大目录
        sorted_dirs = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)[:10]
        stats['largest_dirs'] = [
            {'path': p, 'size': s, 'size_display': FileInfo.format_size(s)}
            for p, s in sorted_dirs
        ]

        return stats

    def _compute_hash(self, filepath: str) -> Optional[str]:
        """计算文件 SHA256 哈希"""
        try:
            sha256 = hashlib.sha256()
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except (OSError, PermissionError):
            return None

    def _categorize(self, extension: str) -> str:
        """分类文件"""
        categories = {
            'video': ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'],
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff'],
            'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'],
            'document': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md'],
            'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'],
            'code': ['.py', '.js', '.java', '.c', '.cpp', '.h', '.go', '.rs', '.ts', '.jsx', '.tsx'],
            'database': ['.db', '.sqlite', '.sql', '.mdb'],
        }

        for category, extensions in categories.items():
            if extension in extensions:
                return category

        return 'other'

    def close(self):
        """关闭数据库连接"""
        if hasattr(self, 'conn'):
            self.conn.close()


def main():
    """演示"""
    import tempfile

    # 创建临时测试目录
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建一些测试文件
        for i in range(5):
            path = os.path.join(tmpdir, f'large_file_{i}.mp4')
            with open(path, 'wb') as f:
                f.write(b'0' * (10 * 1024 * 1024))  # 10MB

        agent = StorageAgent()

        print("=== 大文件分析 ===")
        large_files = agent.analyze_large_files(tmpdir, min_size_mb=1)
        for f in large_files[:3]:
            print(f"{f.size_display} - {f.name}")

        print("\n=== 存储统计 ===")
        stats = agent.get_storage_stats(tmpdir)
        print(f"总文件数: {stats['total_files']}")
        print(f"总大小: {stats['total_size_display']}")


if __name__ == '__main__':
    main()
