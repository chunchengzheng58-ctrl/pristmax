"""
Storage Agent: 智能存储管家 (安全增强版)

功能：
- 大文件分析
- 重复文件检测
- 存储使用统计
- 文件分类整理
- 智能搜索
- 增量扫描
- 导出报告
- 对话交互

安全特性：
- 路径白名单控制
- 只读模式
- 资源限制
- 操作审批流程
- 完整审计日志
"""
import os
import sys
import hashlib
import json
import sqlite3
import time
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from enum import Enum


# ============================================
# 安全配置
# ============================================

class CancellationToken:
    """操作取消令牌"""
    def __init__(self):
        self._cancelled = False

    def cancel(self):
        """请求取消操作"""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def reset(self):
        """重置取消状态"""
        self._cancelled = False


class ProgressTracker:
    """进度跟踪器"""
    def __init__(self, total: int = 0):
        self.total = total
        self.current = 0
        self.start_time = time.time()
        self.errors: List[dict] = []

    def update(self, n: int = 1, message: str = None):
        """更新进度"""
        self.current += n

    def set_total(self, total: int):
        self.total = total

    def add_error(self, error: dict):
        self.errors.append(error)

    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 0
        return (self.current / self.total) * 100

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def to_dict(self) -> dict:
        return {
            'current': self.current,
            'total': self.total,
            'percent': self.progress_percent,
            'elapsed_seconds': self.elapsed_seconds,
            'errors': self.errors
        }


class SecurityConfig:
    """安全配置"""
    def __init__(self):
        # 路径白名单（只允许扫描这些目录）
        self.allowed_paths: List[str] = []

        # 只读模式（禁止任何删除操作）
        self.readonly_mode: bool = True

        # 资源限制
        self.max_scan_files: int = 1000000      # 最多扫描100万文件
        self.max_scan_size_gb: int = 10000       # 最多扫描10TB
        self.max_operation_time: int = 3600       # 单次操作最多1小时
        self.max_file_size_mb: int = 102400       # 单文件最大100GB
        self.max_batch_size: int = 1000           # 批量操作最大数量

        # API 速率限制
        self.api_rate_limit: int = 100            # 每分钟最多100次
        self.api_calls: List[float] = []          # API调用记录

        # 是否启用审批流程
        self.require_approval: bool = True

        # 高危操作需要额外确认
        self.high_risk_confirm: bool = True

        # 操作超时（秒）
        self.operation_timeout: int = 300

    def load_from_env(self):
        """从环境变量加载配置"""
        if os.environ.get('STORAGE_ALLOWED_PATHS'):
            self.allowed_paths = os.environ['STORAGE_ALLOWED_PATHS'].split(',')
        self.readonly_mode = os.environ.get('STORAGE_READONLY', 'true').lower() == 'true'
        self.require_approval = os.environ.get('STORAGE_REQUIRE_APPROVAL', 'true').lower() == 'true'

    def check_rate_limit(self) -> Tuple[bool, str]:
        """检查API速率限制"""
        now = time.time()
        # 清理一分钟前的记录
        self.api_calls = [t for t in self.api_calls if now - t < 60]
        if len(self.api_calls) >= self.api_rate_limit:
            return False, f"API速率限制: 每分钟最多{self.api_rate_limit}次"
        self.api_calls.append(now)
        return True, ""

    def validate_path(self, path: str) -> Tuple[bool, str]:
        """验证路径安全性"""
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return False, f"路径不存在: {path}"
        if not os.path.isdir(abs_path):
            return False, f"路径不是目录: {path}"
        return True, ""

    def to_dict(self) -> dict:
        """导出配置"""
        return {
            'allowed_paths': self.allowed_paths,
            'readonly_mode': self.readonly_mode,
            'require_approval': self.require_approval,
            'max_scan_files': self.max_scan_files,
            'max_scan_size_gb': self.max_scan_size_gb,
            'max_operation_time': self.max_operation_time,
            'max_file_size_mb': self.max_file_size_mb,
            'max_batch_size': self.max_batch_size,
            'api_rate_limit': self.api_rate_limit,
            'high_risk_confirm': self.high_risk_confirm,
            'operation_timeout': self.operation_timeout
        }


# 全局安全配置
_security_config = SecurityConfig()


def set_security_config(
    allowed_paths: List[str] = None,
    readonly: bool = True,
    require_approval: bool = True,
    max_files: int = 1000000,
    max_size_gb: int = 10000
):
    """设置安全配置"""
    if allowed_paths:
        _security_config.allowed_paths = allowed_paths
    _security_config.readonly_mode = readonly
    _security_config.require_approval = require_approval
    _security_config.max_scan_files = max_files
    _security_config.max_scan_size_gb = max_size_gb


# ============================================
# 审批流程
# ============================================

class OperationStatus(Enum):
    """操作状态"""
    PENDING = "pending"      # 待审批
    APPROVED = "approved"   # 已批准
    REJECTED = "rejected"   # 已拒绝
    EXECUTING = "executing" # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"       # 失败


class OperationType(Enum):
    """操作类型"""
    SCAN = "scan"
    ANALYZE = "analyze"
    DELETE_FILES = "delete_files"
    DELETE_DUPLICATES = "delete_duplicates"
    EXPORT_REPORT = "export_report"


@dataclass
class Operation:
    """操作记录"""
    id: str
    type: OperationType
    status: OperationStatus
    path: str
    params: dict
    created_at: str
    approved_at: Optional[str] = None
    executed_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    approved_by: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': self.type.value,
            'status': self.status.value,
            'path': self.path,
            'params': self.params,
            'created_at': self.created_at,
            'approved_at': self.approved_at,
            'executed_at': self.executed_at,
            'completed_at': self.completed_at,
            'result': self.result,
            'error': self.error,
            'approved_by': self.approved_by
        }


class ApprovalManager:
    """审批管理器"""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                path TEXT NOT NULL,
                params TEXT,
                created_at TEXT NOT NULL,
                approved_at TEXT,
                executed_at TEXT,
                completed_at TEXT,
                result TEXT,
                error TEXT,
                approved_by TEXT
            )
        ''')
        self.conn.commit()

    def create_operation(
        self,
        op_type: OperationType,
        path: str,
        params: dict = None
    ) -> Operation:
        """创建操作（待审批）"""
        op_id = f"op_{int(time.time() * 1000)}"
        now = datetime.now().isoformat()

        op = Operation(
            id=op_id,
            type=op_type,
            status=OperationStatus.PENDING,
            path=path,
            params=params or {},
            created_at=now
        )

        self.conn.execute('''
            INSERT INTO operations
            (id, type, status, path, params, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (op_id, op.type.value, op.status.value, path,
              json.dumps(params or {}), now))
        self.conn.commit()

        return op

    def get_operation(self, op_id: str) -> Optional[Operation]:
        """获取操作"""
        cursor = self.conn.execute(
            'SELECT * FROM operations WHERE id = ?', (op_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_operation(row)
        return None

    def list_operations(
        self,
        status: OperationStatus = None,
        limit: int = 50
    ) -> List[Operation]:
        """列出操作"""
        if status:
            cursor = self.conn.execute(
                'SELECT * FROM operations WHERE status = ? ORDER BY created_at DESC LIMIT ?',
                (status.value, limit))
        else:
            cursor = self.conn.execute(
                'SELECT * FROM operations ORDER BY created_at DESC LIMIT ?',
                (limit,))
        return [self._row_to_operation(row) for row in cursor.fetchall()]

    def approve(self, op_id: str, approved_by: str = "system") -> bool:
        """批准操作"""
        now = datetime.now().isoformat()
        self.conn.execute('''
            UPDATE operations
            SET status = ?, approved_at = ?, approved_by = ?
            WHERE id = ? AND status = ?
        ''', (OperationStatus.APPROVED.value, now, approved_by,
              op_id, OperationStatus.PENDING.value))
        self.conn.commit()
        return self.conn.total_changes > 0

    def reject(self, op_id: str, rejected_by: str = "system") -> bool:
        """拒绝操作"""
        now = datetime.now().isoformat()
        self.conn.execute('''
            UPDATE operations
            SET status = ?, approved_at = ?, approved_by = ?
            WHERE id = ? AND status = ?
        ''', (OperationStatus.REJECTED.value, now, rejected_by,
              op_id, OperationStatus.PENDING.value))
        self.conn.commit()
        return self.conn.total_changes > 0

    def complete(self, op_id: str, result: dict = None, error: str = None):
        """完成操作"""
        now = datetime.now().isoformat()
        self.conn.execute('''
            UPDATE operations
            SET status = ?, completed_at = ?, result = ?, error = ?
            WHERE id = ?
        ''', (
            OperationStatus.COMPLETED.value if not error else OperationStatus.FAILED.value,
            now,
            json.dumps(result) if result else None,
            error,
            op_id
        ))
        self.conn.commit()

    def _row_to_operation(self, row) -> Operation:
        return Operation(
            id=row[0],
            type=OperationType(row[1]),
            status=OperationStatus(row[2]),
            path=row[3],
            params=json.loads(row[4]) if row[4] else {},
            created_at=row[5],
            approved_at=row[6],
            executed_at=row[7],
            completed_at=row[8],
            result=json.loads(row[9]) if row[9] else None,
            error=row[10],
            approved_by=row[11]
        )


# ============================================
# 审计日志
# ============================================

class AuditLogger:
    """审计日志"""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                operation TEXT NOT NULL,
                path TEXT,
                details TEXT,
                user TEXT,
                ip TEXT
            )
        ''')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log(timestamp)')
        self.conn.commit()

    def log(self, level: str, operation: str, path: str = None, details: dict = None, user: str = None):
        """记录日志"""
        now = datetime.now().isoformat()
        self.conn.execute('''
            INSERT INTO audit_log (timestamp, level, operation, path, details, user)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (now, level, operation, path, json.dumps(details) if details else None, user))
        self.conn.commit()

    def info(self, operation: str, path: str = None, details: dict = None):
        self.log("INFO", operation, path, details)

    def warning(self, operation: str, path: str = None, details: dict = None):
        self.log("WARNING", operation, path, details)

    def error(self, operation: str, path: str = None, details: dict = None):
        self.log("ERROR", operation, path, details)


# ============================================
# ANSI 颜色码
# ============================================

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
    if sys.platform == 'win32' and not os.environ.get('ANSI_COLORS'):
        return text
    return f"{code}{text}{Colors.RESET}"


# ============================================
# 数据类
# ============================================

@dataclass
class FileInfo:
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
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"


@dataclass
class DuplicateGroup:
    hash: str
    size: int
    size_display: str
    count: int
    files: List[str]
    wasted_space: int


# ============================================
# Storage Agent 核心类
# ============================================

class StorageAgent:
    """
    智能存储管家 Agent (安全增强版)

    核心功能：
    1. 大文件分析 - 找出占用空间最多的文件
    2. 重复文件检测 - 通过哈希检测重复文件
    3. 存储统计 - 各类型文件占用空间
    4. 文件分类 - 按类型自动分类
    """

    # 高危操作类型
    HIGH_RISK_OPERATIONS = [
        OperationType.DELETE_FILES,
        OperationType.DELETE_DUPLICATES
    ]

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()
        self.approval_manager = ApprovalManager(db_path)
        self.audit_logger = AuditLogger(db_path)

    def _init_db(self):
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

    def _check_path_permission(self, path: str) -> bool:
        """检查路径权限"""
        if not _security_config.allowed_paths:
            return True  # 没有配置白名单时允许所有

        abs_path = os.path.abspath(path)
        for allowed in _security_config.allowed_paths:
            allowed_abs = os.path.abspath(allowed)
            if abs_path.startswith(allowed_abs):
                return True
        return False

    def _check_resource_limit(self, path: str) -> Tuple[bool, str]:
        """检查资源限制"""
        # 估算文件数量
        try:
            count = sum(1 for _ in os.scandir(path))
            if count > _security_config.max_scan_files:
                return False, f"文件数量超过限制 ({_security_config.max_scan_files})"
        except:
            pass
        return True, ""

    def _categorize(self, extension: str) -> str:
        """分类文件"""
        ext = extension.lower()
        categories = {
            'video': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'],
            'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'],
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff'],
            'document': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf', '.odt'],
            'code': ['.py', '.js', '.java', '.c', '.cpp', '.h', '.cs', '.go', '.rs', '.php', '.rb', '.swift', '.kt'],
            'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso'],
            'database': ['.db', '.sqlite', '.sqlite3', '.mdb', '.accdb']
        }
        for cat, exts in categories.items():
            if ext in exts:
                return cat
        return 'other'

    def get_storage_stats(
        self,
        root_path: str,
        incremental: bool = True,
        progress: Callable = None
    ) -> dict:
        """获取存储统计"""
        # 权限检查
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        self.audit_logger.info("storage_stats", root_path)

        # 资源限制检查
        allowed, msg = self._check_resource_limit(root_path)
        if not allowed:
            self.audit_logger.warning("resource_limit_exceeded", root_path, {"error": msg})
            raise ValueError(msg)

        files_by_category: Dict[str, Dict] = {}
        files_by_extension: Dict[str, Dict] = {}
        total_files = 0
        total_size = 0
        largest_dirs: List[Dict] = []
        dir_sizes: Dict[str, int] = {}
        scanned = 0

        for dirpath, dirnames, filenames in os.walk(root_path):
            # 跳过隐藏目录
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]

            dir_size = 0

            for filename in filenames:
                if filename.startswith('.'):
                    continue

                filepath = os.path.join(dirpath, filename)
                try:
                    stat = os.path.getsize(filepath)
                    total_files += 1
                    total_size += stat
                    dir_size += stat

                    ext = Path(filename).suffix.lower()
                    category = self._categorize(ext)

                    # 按分类统计
                    if category not in files_by_category:
                        files_by_category[category] = {'count': 0, 'size': 0}
                    files_by_category[category]['count'] += 1
                    files_by_category[category]['size'] += stat

                    # 按扩展名统计
                    if ext not in files_by_extension:
                        files_by_extension[ext] = {'count': 0, 'size': 0}
                    files_by_extension[ext]['count'] += 1
                    files_by_extension[ext]['size'] += stat

                    scanned += 1
                    if progress and scanned % 1000 == 0:
                        progress(scanned, 0, "扫描中...")

                except (OSError, PermissionError):
                    continue

            # 记录目录大小
            if dirpath != root_path:
                dir_sizes[dirpath] = dir_size

        # 按大小排序目录
        largest_dirs = sorted(
            [{'path': p, 'size': s, 'size_display': FileInfo.format_size(s)}
             for p, s in dir_sizes.items()],
            key=lambda x: x['size'],
            reverse=True
        )[:10]

        return {
            'total_files': total_files,
            'total_size': total_size,
            'total_size_display': FileInfo.format_size(total_size),
            'by_category': {
                k: {**v, 'size_display': FileInfo.format_size(v['size'])}
                for k, v in files_by_category.items()
            },
            'by_extension': {
                k: {**v, 'size_display': FileInfo.format_size(v['size'])}
                for k, v in files_by_extension.items()
            },
            'largest_dirs': largest_dirs,
            'scan_type': 'incremental' if incremental else 'full'
        }

    def analyze_large_files(
        self,
        root_path: str,
        min_size_mb: int = 100,
        limit: int = 20
    ) -> List[FileInfo]:
        """分析大文件"""
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        self.audit_logger.info("analyze_large_files", root_path,
                              {"min_size_mb": min_size_mb, "limit": limit})

        min_size = min_size_mb * 1024 * 1024
        results = []

        for dirpath, dirnames, filenames in os.walk(root_path):
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

        results.sort(key=lambda x: x.size, reverse=True)
        return results[:limit]

    def find_duplicates(self, root_path: str, min_size_kb: int = 1) -> List[DuplicateGroup]:
        """查找重复文件"""
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        self.audit_logger.info("find_duplicates", root_path)

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

                    if size not in size_groups:
                        size_groups[size] = []
                    size_groups[size].append(filepath)

                except (OSError, PermissionError):
                    continue

        # 对同大小文件计算哈希
        for size, files in size_groups.items():
            if len(files) < 2:
                continue

            hash_map: Dict[str, List[str]] = {}
            for filepath in files:
                try:
                    with open(filepath, 'rb') as f:
                        file_hash = hashlib.md5(f.read(1024 * 1024)).hexdigest()
                    if file_hash not in hash_map:
                        hash_map[file_hash] = []
                    hash_map[file_hash].append(filepath)
                except:
                    continue

            for h, dup_files in hash_map.items():
                if len(dup_files) > 1:
                    if h not in hash_groups:
                        hash_groups[h] = dup_files
                    else:
                        hash_groups[h].extend(dup_files)

        results = []
        for h, files in hash_groups.items():
            if len(files) > 1:
                file_size = os.path.getsize(files[0])
                wasted = file_size * (len(files) - 1)
                results.append(DuplicateGroup(
                    hash=h,
                    size=file_size,
                    size_display=FileInfo.format_size(file_size),
                    count=len(files),
                    files=files,
                    wasted_space=wasted
                ))

        return sorted(results, key=lambda x: x.wasted_space, reverse=True)

    def get_suggestions(self, root_path: str) -> List[dict]:
        """获取优化建议"""
        if not self._check_path_permission(root_path):
            return []

        self.audit_logger.info("get_suggestions", root_path)

        suggestions = []

        # 统计
        stats = self.get_storage_stats(root_path)

        # 检查大类
        for cat, info in stats.get('by_category', {}).items():
            if info['size'] > 10 * 1024**3:  # > 10GB
                suggestions.append({
                    'type': 'warning',
                    'category': cat,
                    'title': f'{cat.upper()} 类型占用过大',
                    'description': f'{cat} 类型文件共 {info["count"]} 个，占用 {info["size_display"]}',
                    'action': f'建议使用专业压缩工具处理，或迁移到云存储'
                })

        # 检查大目录
        for d in stats.get('largest_dirs', [])[:3]:
            if d['size'] > 50 * 1024**3:  # > 50GB
                suggestions.append({
                    'type': 'tip',
                    'title': f'目录过大: {d["path"][:50]}...',
                    'description': f'占用 {d["size_display"]}',
                    'action': '建议归档或清理'
                })

        return suggestions

    def chat(self, root_path: str, question: str) -> str:
        """自然语言对话"""
        if not self._check_path_permission(root_path):
            return "抱歉，您没有权限访问这个目录"

        self.audit_logger.info("chat", root_path, {"question": question})

        q = question.lower()
        stats = self.get_storage_stats(root_path)

        if any(k in q for k in ['多少', '多少文件', '文件数', 'count']):
            return f"共有 {stats['total_files']:,} 个文件，总大小 {stats['total_size_display']}"

        if any(k in q for k in ['最大', '占用', '最多', 'largest']):
            if stats.get('largest_dirs'):
                d = stats['largest_dirs'][0]
                return f"占用最大的目录是 {d['path']}，共 {d['size_display']}"

        if any(k in q for k in ['视频', 'video']):
            v = stats.get('by_category', {}).get('video', {})
            if v:
                return f"视频文件共 {v['count']} 个，占用 {v.get('size_display', 'N/A')}"

        return "我可以帮您分析存储情况，请告诉我您想了解什么？"

    def cleanup_duplicates(
        self,
        root_path: str,
        dry_run: bool = True,
        auto_approve: bool = False,
        cancel_token: CancellationToken = None,
        progress_callback: Callable = None
    ) -> dict:
        """
        清理重复文件（安全模式）

        Args:
            root_path: 扫描目录
            dry_run: True=仅预览，False=实际删除
            auto_approve: True=跳过审批（仅当 readonly_mode=False 时）
            cancel_token: 取消令牌，用于中断长时间操作
            progress_callback: 进度回调函数
        """
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        # 只读模式禁止删除
        if not dry_run and _security_config.readonly_mode:
            self.audit_logger.warning("cleanup_blocked_readonly", root_path)
            return {'error': '只读模式已启用，禁止删除操作'}

        # 高危操作需要审批
        if not dry_run and _security_config.require_approval and not auto_approve:
            # 创建待审批操作
            op = self.approval_manager.create_operation(
                OperationType.DELETE_DUPLICATES,
                root_path,
                {'dry_run': dry_run}
            )
            self.audit_logger.info("cleanup_pending_approval", root_path,
                                  {'operation_id': op.id})
            return {
                'status': 'pending_approval',
                'operation_id': op.id,
                'message': f'删除操作已提交，等待审批。操作ID: {op.id}'
            }

        self.audit_logger.info("cleanup_duplicates", root_path, {'dry_run': dry_run})

        duplicates = self.find_duplicates(root_path)

        files_to_delete = []
        for group in duplicates:
            # 保留第一个，标记其余为待删除
            files_to_delete.extend(group.files[1:])

        # 批量大小限制
        if len(files_to_delete) > _security_config.max_batch_size:
            files_to_delete = files_to_delete[:_security_config.max_batch_size]

        deleted = []
        errors = []
        tracker = ProgressTracker(total=len(files_to_delete))

        if not dry_run:
            for i, filepath in enumerate(files_to_delete):
                # 检查取消
                if cancel_token and cancel_token.is_cancelled:
                    self.audit_logger.warning("cleanup_cancelled", root_path,
                                            {'deleted': len(deleted), 'remaining': len(files_to_delete) - i})
                    break

                try:
                    os.remove(filepath)
                    deleted.append(filepath)
                    self.audit_logger.info("file_deleted", filepath)
                    tracker.update(1, filepath)
                except Exception as e:
                    errors.append({'file': filepath, 'error': str(e)})
                    tracker.add_error({'file': filepath, 'error': str(e)})
                    self.audit_logger.error("delete_failed", filepath, {'error': str(e)})

                # 进度回调
                if progress_callback and i % 10 == 0:
                    progress_callback(tracker.to_dict())

        space_freed = sum(os.path.getsize(f) for f in deleted if os.path.exists(f))

        return {
            'groups_found': len(duplicates),
            'files_to_delete': files_to_delete,
            'deleted': deleted,
            'deleted_count': len(deleted),
            'errors': errors,
            'error_count': len(errors),
            'space_to_free': sum(d.wasted_space for d in duplicates),
            'space_freed': space_freed,
            'dry_run': dry_run,
            'cancelled': cancel_token.is_cancelled if cancel_token else False,
            'progress': tracker.to_dict()
        }

    def cleanup_large_files(
        self,
        root_path: str,
        min_size_mb: int = 100,
        dry_run: bool = True,
        auto_approve: bool = False,
        cancel_token: CancellationToken = None,
        progress_callback: Callable = None
    ) -> dict:
        """清理大文件（安全模式）"""
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        if not dry_run and _security_config.readonly_mode:
            self.audit_logger.warning("cleanup_blocked_readonly", root_path)
            return {'error': '只读模式已启用，禁止删除操作'}

        # 审批流程
        if not dry_run and _security_config.require_approval and not auto_approve:
            op = self.approval_manager.create_operation(
                OperationType.DELETE_FILES,
                root_path,
                {'min_size_mb': min_size_mb, 'dry_run': dry_run}
            )
            return {
                'status': 'pending_approval',
                'operation_id': op.id,
                'message': f'删除操作已提交，等待审批。操作ID: {op.id}'
            }

        self.audit_logger.info("cleanup_large_files", root_path,
                              {'min_size_mb': min_size_mb, 'dry_run': dry_run})

        large_files = self.analyze_large_files(root_path, min_size_mb=min_size_mb, limit=1000)
        files_to_delete = [f.path for f in large_files]

        # 批量大小限制
        if len(files_to_delete) > _security_config.max_batch_size:
            files_to_delete = files_to_delete[:_security_config.max_batch_size]

        deleted = []
        errors = []
        tracker = ProgressTracker(total=len(files_to_delete))

        if not dry_run:
            for i, filepath in enumerate(files_to_delete):
                # 检查取消
                if cancel_token and cancel_token.is_cancelled:
                    self.audit_logger.warning("cleanup_cancelled", root_path,
                                            {'deleted': len(deleted), 'remaining': len(files_to_delete) - i})
                    break

                try:
                    os.remove(filepath)
                    deleted.append(filepath)
                    self.audit_logger.info("file_deleted", filepath)
                    tracker.update(1, filepath)
                except Exception as e:
                    errors.append({'file': filepath, 'error': str(e)})
                    tracker.add_error({'file': filepath, 'error': str(e)})

                # 进度回调
                if progress_callback and i % 10 == 0:
                    progress_callback(tracker.to_dict())

        space_freed = sum(os.path.getsize(f) for f in deleted if os.path.exists(f))

        return {
            'files_found': len(large_files),
            'files_to_delete': files_to_delete,
            'deleted': deleted,
            'deleted_count': len(deleted),
            'errors': errors,
            'error_count': len(errors),
            'space_to_free': sum(f.size for f in large_files),
            'space_freed': space_freed,
            'dry_run': dry_run,
            'cancelled': cancel_token.is_cancelled if cancel_token else False,
            'progress': tracker.to_dict()
        }

    def export_report(
        self,
        root_path: str,
        output_path: str,
        format: str = 'html'
    ) -> dict:
        """导出报告"""
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        self.audit_logger.info("export_report", root_path,
                              {'output': output_path, 'format': format})

        stats = self.get_storage_stats(root_path)
        suggestions = self.get_suggestions(root_path)

        if format == 'json':
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({'stats': stats, 'suggestions': suggestions}, f, indent=2, ensure_ascii=False)
        else:  # html
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Storage Report - {root_path}</title>
    <style>
        body {{ font-family: system-ui; max-width: 800px; margin: 40px auto; padding: 20px; }}
        h1 {{ color: #113577; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f4f9fc; }}
        .warning {{ color: #d4af37; }}
        .tip {{ color: #4caf50; }}
    </style>
</head>
<body>
    <h1>存储分析报告</h1>
    <p>路径: {root_path}</p>
    <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    <h2>概览</h2>
    <table>
        <tr><th>总文件数</th><td>{stats['total_files']:,}</td></tr>
        <tr><th>总大小</th><td>{stats['total_size_display']}</td></tr>
    </table>

    <h2>类型分布</h2>
    <table>
        <tr><th>类型</th><th>文件数</th><th>大小</th></tr>
"""
            for cat, info in sorted(stats.get('by_category', {}).items(),
                                    key=lambda x: x[1]['size'], reverse=True):
                html += f"""        <tr><td>{cat}</td><td>{info['count']:,}</td><td>{info.get('size_display', 'N/A')}</td></tr>
"""

            html += """    </table>

    <h2>优化建议</h2>
    <ul>
"""
            for s in suggestions:
                html += f"""        <li class="{s.get('type', 'info')}">{s.get('title', '')} - {s.get('description', '')}</li>
"""

            html += """    </ul>
</body>
</html>"""

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)

        return {'output': output_path, 'format': format}

    def safe_delete(
        self,
        file_path: str,
        trash_dir: str = None
    ) -> dict:
        """
        安全删除：将文件移动到回收站而不是直接删除

        Args:
            file_path: 要删除的文件路径
            trash_dir: 回收站目录（默认使用系统临时目录）
        """
        if _security_config.readonly_mode:
            return {'error': '只读模式已启用，禁止删除操作'}

        if not os.path.exists(file_path):
            return {'error': f'文件不存在: {file_path}'}

        # 创建回收站目录
        if not trash_dir:
            trash_dir = os.path.join(os.path.expanduser('~'), '.pristmax_trash')
        os.makedirs(trash_dir, exist_ok=True)

        # 生成安全文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.basename(file_path)
        safe_name = f"{timestamp}_{filename}"
        trash_path = os.path.join(trash_dir, safe_name)

        try:
            # 如果目标已存在，添加序号
            counter = 1
            while os.path.exists(trash_path):
                safe_name = f"{timestamp}_{counter}_{filename}"
                trash_path = os.path.join(trash_dir, safe_name)
                counter += 1

            # 移动到回收站
            os.rename(file_path, trash_path)
            self.audit_logger.info("safe_delete", file_path, {'trash_path': trash_path})

            return {
                'success': True,
                'original_path': file_path,
                'trash_path': trash_path,
                'message': f'文件已移动到回收站: {trash_path}'
            }
        except Exception as e:
            self.audit_logger.error("safe_delete_failed", file_path, {'error': str(e)})
            return {'error': str(e)}

    def restore_from_trash(self, trash_path: str, target_dir: str = None) -> dict:
        """从回收站恢复文件"""
        if not os.path.exists(trash_path):
            return {'error': f'回收站文件不存在: {trash_path}'}

        if target_dir is None:
            target_dir = os.path.dirname(trash_path)

        filename = os.path.basename(trash_path)
        # 移除时间戳前缀
        if '_' in filename:
            parts = filename.split('_', 2)
            if len(parts) >= 3:
                filename = parts[2]

        target_path = os.path.join(target_dir, filename)

        try:
            os.rename(trash_path, target_path)
            self.audit_logger.info("restore_from_trash", trash_path, {'target': target_path})
            return {
                'success': True,
                'trash_path': trash_path,
                'restored_path': target_path,
                'message': f'文件已恢复到: {target_path}'
            }
        except Exception as e:
            self.audit_logger.error("restore_failed", trash_path, {'error': str(e)})
            return {'error': str(e)}

    def get_operation_stats(self) -> dict:
        """获取操作统计"""
        cursor = self.approval_manager.conn.execute('''
            SELECT status, type, COUNT(*) as count,
                   SUM(CASE WHEN result IS NOT NULL THEN json_extract(result, '$.space_freed') ELSE 0 END) as space_freed
            FROM operations
            GROUP BY status, type
        ''')

        stats = {
            'total': 0,
            'by_status': {},
            'by_type': {},
            'total_space_freed': 0
        }

        for row in cursor.fetchall():
            status, op_type, count, space_freed = row
            stats['total'] += count
            stats['by_status'][status] = stats['by_status'].get(status, 0) + count
            stats['by_type'][op_type] = stats['by_type'].get(op_type, 0) + count
            if space_freed:
                stats['total_space_freed'] += space_freed

        return stats

    def get_recent_operations(self, limit: int = 10) -> List[Operation]:
        """获取最近操作"""
        return self.approval_manager.list_operations(limit=limit)

    def close(self):
        """关闭连接"""
        if hasattr(self, 'conn'):
            self.conn.close()


# ============================================
# MCP 工具定义
# ============================================

def get_mcp_tools():
    """获取 MCP 工具列表"""
    return [
        {
            'name': 'storage_stats',
            'description': '获取目录存储统计（只读操作，无需审批）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'},
                    'incremental': {'type': 'boolean', 'description': '使用增量扫描', 'default': True}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_large_files',
            'description': '查找大文件（只读操作，无需审批）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'},
                    'min_size_mb': {'type': 'integer', 'description': '最小文件大小(MB)', 'default': 100},
                    'limit': {'type': 'integer', 'description': '返回数量', 'default': 20}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_duplicates',
            'description': '查找重复文件（只读操作，无需审批）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'},
                    'min_size_kb': {'type': 'integer', 'description': '最小文件大小(KB)', 'default': 1}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_suggestions',
            'description': '获取优化建议（只读操作，无需审批）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_cleanup_preview',
            'description': '预览清理操作（不实际删除，仅预览）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'},
                    'type': {'type': 'string', 'enum': ['duplicates', 'large'], 'description': '清理类型'},
                    'min_size_mb': {'type': 'integer', 'description': '大文件最小大小(MB)', 'default': 100}
                },
                'required': ['path', 'type']
            }
        },
        {
            'name': 'storage_cleanup_execute',
            'description': '执行清理操作（需审批，高危）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'operation_id': {'type': 'string', 'description': '审批通过的操作ID'},
                    'confirm': {'type': 'boolean', 'description': '确认执行'}
                },
                'required': ['operation_id', 'confirm']
            }
        },
        {
            'name': 'storage_approval_query',
            'description': '查询待审批操作',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string', 'enum': ['pending', 'approved', 'rejected'], 'description': '状态筛选'}
                }
            }
        },
        {
            'name': 'storage_approval_action',
            'description': '审批操作（批准/拒绝）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'operation_id': {'type': 'string', 'description': '操作ID'},
                    'action': {'type': 'string', 'enum': ['approve', 'reject'], 'description': '审批动作'},
                    'approved_by': {'type': 'string', 'description': '审批人'}
                },
                'required': ['operation_id', 'action']
            }
        }
    ]
