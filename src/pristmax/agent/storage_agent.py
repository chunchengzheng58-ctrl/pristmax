"""
Storage Agent: 智能存储管家

功能：
- 大文件分析
- 重复文件检测
- 存储使用统计
- 文件分类整理
- 智能搜索
- 增量扫描
- 导出报告
- 对话交互
"""
import os
import sys
import hashlib
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, asdict


# ANSI 颜色码
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'


def color(text: str, code: str) -> str:
    """给文本添加颜色"""
    if sys.platform == 'win32' and not os.environ.get('ANSI_COLORS'):
        return text
    return f"{code}{text}{Colors.RESET}"


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

    def get_storage_stats(self, root_path: str, incremental: bool = True, progress: Optional[Callable] = None) -> Dict:
        """
        获取存储统计

        Args:
            root_path: 扫描根目录
            incremental: 是否使用增量扫描（默认True，使用缓存）
            progress: 进度回调函数 callback(current, total, message)

        Returns:
            统计信息
        """
        stats = {
            'total_files': 0,
            'total_size': 0,
            'total_size_display': '0 B',
            'by_category': {},
            'by_extension': {},
            'largest_dirs': [],
            'scan_type': 'incremental' if incremental else 'full',
            'cached_files': 0,
            'new_files': 0
        }

        # 先快速统计文件总数
        total_files = sum(1 for _, _, files in os.walk(root_path) for f in files if not f.startswith('.'))

        dir_sizes: Dict[str, int] = {}
        now = datetime.now().isoformat()
        processed = 0

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            dir_size = 0

            for filename in filenames:
                if filename.startswith('.'):
                    continue

                filepath = os.path.join(dirpath, filename)
                processed += 1
                if progress and total_files > 0:
                    progress(processed, total_files, f"扫描: {filename[:40]}")

                try:
                    size = os.path.getsize(filepath)
                    stat = os.stat(filepath)
                    mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()

                    # 增量扫描：检查缓存
                    if incremental:
                        cached = self._get_cached_file(filepath)
                        if cached and cached['modified'] == mtime and cached['size'] == size:
                            # 文件未变化，使用缓存
                            stats['total_files'] += 1
                            stats['total_size'] += size
                            dir_size += size
                            category = cached['category']
                            ext = cached['extension']
                            stats['cached_files'] += 1
                        else:
                            # 文件变化或无缓存，重新扫描
                            ext = Path(filename).suffix.lower() or '.none'
                            category = self._categorize(ext)
                            self._update_cache(filepath, filename, size, ext, category, mtime, stat)
                            stats['total_files'] += 1
                            stats['total_size'] += size
                            dir_size += size
                            stats['new_files'] += 1
                    else:
                        # 全量扫描
                        ext = Path(filename).suffix.lower() or '.none'
                        category = self._categorize(ext)
                        stats['total_files'] += 1
                        stats['total_size'] += size
                        dir_size += size

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

    def _get_cached_file(self, filepath: str) -> Optional[Dict]:
        """获取缓存的文件信息"""
        cursor = self.conn.execute(
            "SELECT name, size, extension, category, modified, hash FROM file_cache WHERE path = ?",
            (filepath,)
        )
        row = cursor.fetchone()
        if row:
            return {
                'name': row[0],
                'size': row[1],
                'extension': row[2],
                'category': row[3],
                'modified': row[4],
                'hash': row[5]
            }
        return None

    def _update_cache(self, filepath: str, name: str, size: int, ext: str, category: str, modified: str, stat):
        """更新文件缓存"""
        created = datetime.fromtimestamp(stat.st_ctime).isoformat()
        self.conn.execute('''
            INSERT OR REPLACE INTO file_cache (path, name, size, extension, category, modified, created, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (filepath, name, size, ext, category, modified, created, datetime.now().isoformat()))
        self.conn.commit()

    def export_report(self, root_path: str, output_path: str, format: str = 'html') -> str:
        """
        导出分析报告

        Args:
            root_path: 扫描目录
            output_path: 输出文件路径
            format: 报告格式 ('html' 或 'json')

        Returns:
            报告文件路径
        """
        stats = self.get_storage_stats(root_path, incremental=True)

        if format == 'json':
            return self._export_json(stats, output_path)
        else:
            return self._export_html(stats, root_path, output_path)

    def _export_json(self, stats: Dict, output_path: str) -> str:
        """导出 JSON 格式报告"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        return output_path

    def _export_html(self, stats: Dict, root_path: str, output_path: str) -> str:
        """导出 HTML 格式报告"""
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>Storage Report - {root_path}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ color: #173d58; margin-bottom: 10px; }}
        .meta {{ color: #666; font-size: 14px; margin-bottom: 30px; }}
        .card {{ background: white; border-radius: 8px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .card h2 {{ color: #173d58; font-size: 18px; margin-bottom: 16px; border-bottom: 2px solid #d4af37; padding-bottom: 8px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }}
        .stat-item {{ text-align: center; padding: 16px; background: #f8f9fa; border-radius: 6px; }}
        .stat-value {{ font-size: 28px; font-weight: bold; color: #173d58; }}
        .stat-label {{ font-size: 12px; color: #666; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 12px 8px; border-bottom: 1px solid #eee; }}
        th {{ color: #666; font-weight: 600; font-size: 12px; text-transform: uppercase; }}
        .category-bar {{ display: flex; align-items: center; gap: 12px; margin: 8px 0; }}
        .category-name {{ width: 80px; font-size: 13px; }}
        .category-size {{ width: 80px; text-align: right; font-size: 13px; color: #666; }}
        .bar-bg {{ flex: 1; height: 8px; background: #eee; border-radius: 4px; }}
        .bar-fill {{ height: 100%; background: linear-gradient(90deg, #d4af37, #173d58); border-radius: 4px; }}
        .scan-type {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 11px; background: #e8f4e8; color: #2e7d32; }}
        .scan-type.full {{ background: #fff3e0; color: #e65100; }}
        .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Storage Report</h1>
        <p class="meta">Scan: {root_path} · Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>

        <div class="card">
            <h2>Overview 总览</h2>
            <span class="scan-type {'full' if stats['scan_type'] == 'full' else ''}">{stats['scan_type']}</span>
            <div class="stats-grid" style="margin-top: 16px;">
                <div class="stat-item">
                    <div class="stat-value">{stats['total_files']:,}</div>
                    <div class="stat-label">Total Files</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{stats['total_size_display']}</div>
                    <div class="stat-label">Total Size</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{stats.get('cached_files', 0):,}</div>
                    <div class="stat-label">Cached (unchanged)</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{stats.get('new_files', 0):,}</div>
                    <div class="stat-label">New/Changed</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>By Category 类型分布</h2>
            {self._render_category_bars(stats)}
        </div>

        <div class="card">
            <h2>Largest Directories 最大目录</h2>
            <table>
                <thead>
                    <tr>
                        <th>Path</th>
                        <th style="text-align:right;">Size</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(f'<tr><td>{d["path"]}</td><td style="text-align:right;color:#666;">{d["size_display"]}</td></tr>' for d in stats['largest_dirs'][:10])}
                </tbody>
            </table>
        </div>

        <div class="footer">
            Generated by Pristmax Storage Agent
        </div>
    </div>
</body>
</html>'''
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return output_path

    def _render_category_bars(self, stats: Dict) -> str:
        """渲染分类条形图"""
        if not stats['by_category']:
            return '<p style="color:#666;">No data</p>'

        max_size = max(cat['size'] for cat in stats['by_category'].values())

        bars = []
        for cat, info in sorted(stats['by_category'].items(), key=lambda x: x[1]['size'], reverse=True):
            pct = int(info['size'] / max_size * 100) if max_size > 0 else 0
            bars.append(f'''
            <div class="category-bar">
                <span class="category-name">{cat}</span>
                <div class="bar-bg"><div class="bar-fill" style="width:{pct}%"></div></div>
                <span class="category-size">{info['size_display']}</span>
            </div>
            ''')
        return ''.join(bars)

    def get_suggestions(self, root_path: str) -> List[Dict]:
        """
        根据分析结果生成智能建议

        Returns:
            建议列表，每条建议包含 type, title, description, action
        """
        suggestions = []
        stats = self.get_storage_stats(root_path, incremental=True)
        large_files = self.analyze_large_files(root_path, min_size_mb=100, limit=10)
        duplicates = self.find_duplicates(root_path, min_size_kb=1024)

        # 重复文件建议
        if duplicates:
            total_wasted = sum(d.wasted_space for d in duplicates[:5])
            suggestions.append({
                'type': 'warning',
                'icon': '🔄',
                'title': f'发现 {len(duplicates)} 组重复文件',
                'description': f'可节省空间: {FileInfo.format_size(total_wasted)}',
                'action': f'运行 --duplicates 查看详情'
            })

        # 大文件建议
        if large_files:
            total_large = sum(f.size for f in large_files)
            suggestions.append({
                'type': 'info',
                'icon': '📦',
                'title': f'发现 {len(large_files)} 个大文件 (>100MB)',
                'description': f'总占用: {FileInfo.format_size(total_large)}',
                'action': f'运行 --large-files --min 100 查看详情'
            })

        # 按类型分析建议
        if stats['by_category']:
            top_cat = max(stats['by_category'].items(), key=lambda x: x[1]['size'])
            cat_pct = int(top_cat[1]['size'] / stats['total_size'] * 100) if stats['total_size'] > 0 else 0
            if cat_pct > 50:
                suggestions.append({
                    'type': 'tip',
                    'icon': '💡',
                    'title': f'{top_cat[0]} 类型占比过高 ({cat_pct}%)',
                    'description': f'占用空间: {top_cat[1]["size_display"]}',
                    'action': '考虑压缩或归档该类型文件'
                })

        # 空文件检查
        if stats['total_files'] > 1000:
            suggestions.append({
                'type': 'tip',
                'icon': '📊',
                'title': f'文件数量较多 ({stats["total_files"]:,} 个)',
                'description': '建议定期清理或归档',
                'action': '使用 --export 生成报告进行详细分析'
            })

        return suggestions

    def chat(self, root_path: str, message: str) -> str:
        """
        处理自然语言对话

        Args:
            root_path: 扫描目录
            message: 用户消息

        Returns:
            响应消息
        """
        msg = message.lower().strip()

        # 大文件相关
        if any(k in msg for k in ['大文件', 'large file', 'big file']):
            large_files = self.analyze_large_files(root_path, min_size_mb=50, limit=10)
            if large_files:
                result = f"📦 找到 {len(large_files)} 个大文件 (>50MB):\n\n"
                for f in large_files:
                    result += f"  • {f.size_display} - {f.name}\n"
                return result
            return "✅ 未找到大于 50MB 的文件"

        # 重复文件相关
        if any(k in msg for k in ['重复', 'duplicate', 'same']):
            duplicates = self.find_duplicates(root_path, min_size_kb=1024)
            if duplicates:
                result = f"🔄 找到 {len(duplicates)} 组重复文件:\n\n"
                for i, d in enumerate(duplicates[:5], 1):
                    result += f"  组 {i}: {d.count} 个文件，可节省 {d.size_display}\n"
                return result
            return "✅ 未找到重复文件"

        # 统计相关
        if any(k in msg for k in ['统计', 'statistic', '分析', 'analyze']):
            stats = self.get_storage_stats(root_path)
            result = f"📊 存储统计: {root_path}\n\n"
            result += f"  总文件: {stats['total_files']:,}\n"
            result += f"  总大小: {stats['total_size_display']}\n\n"
            result += "  按类型分布:\n"
            for cat, info in sorted(stats['by_category'].items(), key=lambda x: x[1]['size'], reverse=True)[:5]:
                result += f"    • {cat}: {info['size_display']}\n"
            return result

        # 建议相关
        if any(k in msg for k in ['建议', 'suggest', 'tip', 'help']):
            suggestions = self.get_suggestions(root_path)
            if suggestions:
                result = "💡 智能建议:\n\n"
                for s in suggestions:
                    result += f"  {s['icon']} {s['title']}\n    {s['description']}\n    → {s['action']}\n\n"
                return result
            return "✅ 目前没有需要关注的建议"

        # 帮助
        if any(k in msg for k in ['help', '帮助', '命令', 'command']):
            return """🤖 可用命令:
  • "大文件" / "large files" - 查找大文件
  • "重复文件" / "duplicates" - 查找重复文件
  • "统计" / "stats" - 显示存储统计
  • "建议" / "suggestions" - 获取优化建议
  • "帮助" / "help" - 显示此帮助信息"""

        # 默认
        return f"""🤔 我不太理解 "{message}"

可用的命令:
  • "大文件" - 查找大文件
  • "重复文件" - 查找重复文件
  • "统计" - 显示存储统计
  • "建议" - 获取优化建议
  • "帮助" - 显示所有命令"""

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
