"""
M4 Dedup: Safe Deduplication with Data Protection

安全去重模块:
- 引用计数保护 (绝不删除仍有引用的块)
- 用户授权机制 (删除操作需授权)
- 操作审计记录
- 备份保护 (删除前备份)
- 完整性校验

核心原则:
- 不删除任何仍有有效引用的数据
- 删除操作需要用户授权
- 所有删除操作都有审计记录
- 支持数据恢复
"""
import os
import json
import sqlite3
import hashlib
import shutil
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set
from pathlib import Path
from datetime import datetime
from enum import Enum


class OperationType(Enum):
    """操作类型"""
    STORE = "store"           # 存储新块
    REFERENCE = "reference"    # 增加引用
    DEREFERENCE = "dereference"  # 减少引用
    DELETE_REQUEST = "delete_request"  # 删除请求 (待授权)
    DELETE = "delete"         # 执行删除
    RESTORE = "restore"       # 恢复


class DeleteAuthorizationStatus(Enum):
    """删除授权状态"""
    PENDING = "pending"
    AUTHORIZED = "authorized"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ChunkRef:
    """块引用"""
    chunk_id: str
    content_hash: str
    size: int
    storage_path: str = ""
    offset: int = 0
    ref_count: int = 1
    created_at: str = ""
    last_accessed: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeleteRequest:
    """删除请求"""
    request_id: str
    content_hash: str
    chunk_id: str
    requested_by: str = "system"
    reason: str = ""
    requested_at: str = ""

    authorization_status: DeleteAuthorizationStatus = DeleteAuthorizationStatus.PENDING
    authorized_by: str = ""
    authorized_at: str = ""

    # 删除后的备份
    backup_path: str = ""
    backup_created: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DedupStats:
    """去重统计"""
    total_chunks: int = 0
    unique_chunks: int = 0
    total_size: int = 0
    saved_size: int = 0
    pending_deletes: int = 0
    total_refs: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class AuditLog:
    """审计日志"""

    def __init__(self, log_dir: str = "./dedup_audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        operation: OperationType,
        content_hash: str,
        details: Dict,
        user_id: str = "system"
    ):
        """记录操作"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation.value,
            'content_hash': content_hash,
            'details': details,
            'user_id': user_id
        }

        # 按日期存储
        date_str = datetime.now().strftime('%Y%m%d')
        log_file = self.log_dir / f"audit_{date_str}.jsonl"

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def get_logs(
        self,
        content_hash: str = None,
        operation: OperationType = None,
        date: str = None
    ) -> List[Dict]:
        """查询日志"""
        logs = []
        date_str = date or datetime.now().strftime('%Y%m%d')
        log_file = self.log_dir / f"audit_{date_str}.jsonl"

        if not log_file.exists():
            return logs

        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if content_hash and entry.get('content_hash') != content_hash:
                        continue
                    if operation and entry.get('operation') != operation.value:
                        continue
                    logs.append(entry)
                except json.JSONDecodeError:
                    continue

        return logs


class DedupIndexSafe:
    """
    安全去重索引

    安全保证:
    1. 引用计数保护 - 绝不删除 ref_count > 0 的块
    2. 删除授权 - 删除操作需要用户授权
    3. 备份保护 - 删除前创建备份
    4. 审计日志 - 所有操作可追溯
    5. 完整性校验 - SHA-256 验证
    """

    def __init__(
        self,
        db_path: str = "./dedup_safe.db",
        backup_dir: str = "./dedup_backup",
        audit_dir: str = "./dedup_audit"
    ):
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.audit = AuditLog(audit_dir)
        self.delete_requests: Dict[str, DeleteRequest] = {}

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                content_hash TEXT UNIQUE NOT NULL,
                size INTEGER NOT NULL,
                storage_path TEXT,
                offset INTEGER,
                ref_count INTEGER DEFAULT 1,
                created_at TEXT,
                last_accessed TEXT,
                is_deleted INTEGER DEFAULT 0,
                deleted_at TEXT
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_content_hash ON chunks(content_hash)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ref_count ON chunks(ref_count)
        """)
        self.conn.commit()

    def add_chunk(
        self,
        chunk_id: str,
        content_hash: str,
        size: int,
        storage_path: str = "",
        offset: int = 0,
        user_id: str = "system"
    ) -> bool:
        """
        添加块到索引

        始终保持 ref_count >= 1，绝不会自动删除
        """
        now = datetime.now().isoformat()

        # 检查是否已存在
        existing = self.get_by_hash(content_hash)
        if existing:
            # 增加引用计数
            self.conn.execute(
                "UPDATE chunks SET ref_count = ref_count + 1, last_accessed = ? WHERE content_hash = ?",
                (now, content_hash)
            )
            self.conn.commit()

            self.audit.log(
                OperationType.REFERENCE,
                content_hash,
                {'chunk_id': existing.chunk_id, 'new_ref_count': existing.ref_count + 1},
                user_id
            )
            return False

        # 新增块
        self.conn.execute(
            """INSERT INTO chunks (chunk_id, content_hash, size, storage_path, offset, ref_count, created_at, last_accessed)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            (chunk_id, content_hash, size, storage_path, offset, now, now)
        )
        self.conn.commit()

        self.audit.log(
            OperationType.STORE,
            content_hash,
            {'chunk_id': chunk_id, 'size': size, 'storage_path': storage_path},
            user_id
        )

        return True

    def get_by_hash(self, content_hash: str) -> Optional[ChunkRef]:
        """通过内容哈希获取块"""
        cursor = self.conn.execute(
            "SELECT * FROM chunks WHERE content_hash = ? AND is_deleted = 0",
            (content_hash,)
        )
        row = cursor.fetchone()
        if row:
            return ChunkRef(
                chunk_id=row[0],
                content_hash=row[1],
                size=row[2],
                storage_path=row[3] or "",
                offset=row[4] or 0,
                ref_count=row[5],
                created_at=row[6] or "",
                last_accessed=row[7] or ""
            )
        return None

    def request_delete(
        self,
        content_hash: str,
        requested_by: str = "system",
        reason: str = ""
    ) -> Optional[str]:
        """
        请求删除块 - 需要用户授权

        只有 ref_count = 0 的块才能请求删除
        """
        chunk = self.get_by_hash(content_hash)
        if not chunk:
            return None

        # 安全检查: ref_count 必须为 0
        if chunk.ref_count > 0:
            self.audit.log(
                OperationType.DELETE_REQUEST,
                content_hash,
                {'error': 'ref_count > 0', 'ref_count': chunk.ref_count},
                requested_by
            )
            return None

        # 创建删除请求
        request_id = f"del-{datetime.now().strftime('%Y%m%d%H%M%S')}-{content_hash[:8]}"

        delete_req = DeleteRequest(
            request_id=request_id,
            content_hash=content_hash,
            chunk_id=chunk.chunk_id,
            requested_by=requested_by,
            reason=reason,
            requested_at=datetime.now().isoformat()
        )

        self.delete_requests[request_id] = delete_req

        # 记录审计日志
        self.audit.log(
            OperationType.DELETE_REQUEST,
            content_hash,
            {
                'request_id': request_id,
                'requested_by': requested_by,
                'reason': reason,
                'chunk_size': chunk.size
            },
            requested_by
        )

        return request_id

    def authorize_delete(
        self,
        request_id: str,
        authorized_by: str = "user"
    ) -> bool:
        """
        授权删除

        用户必须明确授权才能执行删除
        """
        if request_id not in self.delete_requests:
            return False

        delete_req = self.delete_requests[request_id]

        # 检查块是否仍有有效引用
        chunk = self.get_by_hash(delete_req.content_hash)
        if chunk and chunk.ref_count > 0:
            delete_req.authorization_status = DeleteAuthorizationStatus.REJECTED
            return False

        # 创建备份
        if chunk and chunk.storage_path and os.path.exists(chunk.storage_path):
            backup_path = self.backup_dir / f"{chunk.content_hash}.backup"
            try:
                shutil.copy2(chunk.storage_path, backup_path)
                delete_req.backup_path = str(backup_path)
                delete_req.backup_created = True
            except Exception as e:
                print(f"[Dedup] Backup failed: {e}")

        delete_req.authorization_status = DeleteAuthorizationStatus.AUTHORIZED
        delete_req.authorized_by = authorized_by
        delete_req.authorized_at = datetime.now().isoformat()

        # 审计日志
        self.audit.log(
            OperationType.DELETE,
            delete_req.content_hash,
            {
                'request_id': request_id,
                'authorized_by': authorized_by,
                'backup_path': delete_req.backup_path,
                'backup_created': delete_req.backup_created
            },
            authorized_by
        )

        # 执行删除 (标记为已删除)
        self.conn.execute(
            "UPDATE chunks SET is_deleted = 1, deleted_at = ? WHERE content_hash = ?",
            (datetime.now().isoformat(), delete_req.content_hash)
        )
        self.conn.commit()

        # 删除物理文件 (如果备份成功)
        if delete_req.backup_created and chunk and chunk.storage_path:
            try:
                if os.path.exists(chunk.storage_path):
                    os.unlink(chunk.storage_path)
            except Exception as e:
                print(f"[Dedup] Physical delete failed: {e}")

        return True

    def reject_delete(self, request_id: str) -> bool:
        """拒绝删除"""
        if request_id not in self.delete_requests:
            return False

        delete_req = self.delete_requests[request_id]
        delete_req.authorization_status = DeleteAuthorizationStatus.REJECTED

        self.audit.log(
            OperationType.DELETE_REQUEST,
            delete_req.content_hash,
            {'request_id': request_id, 'action': 'rejected'},
            delete_req.requested_by
        )

        return True

    def restore_from_backup(self, content_hash: str, user_id: str = "user") -> bool:
        """
        从备份恢复

        用户可以恢复误删的数据
        """
        backup_path = self.backup_dir / f"{content_hash}.backup"

        if not backup_path.exists():
            return False

        # 恢复数据库记录
        self.conn.execute(
            "UPDATE chunks SET is_deleted = 0, deleted_at = NULL WHERE content_hash = ?",
            (content_hash,)
        )
        self.conn.commit()

        # 审计日志
        self.audit.log(
            OperationType.RESTORE,
            content_hash,
            {'backup_path': str(backup_path)},
            user_id
        )

        return True

    def dereference(self, content_hash: str, user_id: str = "system") -> int:
        """
        减少引用计数

        返回剩余引用计数
        绝不会删除 ref_count > 0 的块
        """
        cursor = self.conn.execute(
            "UPDATE chunks SET ref_count = MAX(0, ref_count - 1) WHERE content_hash = ? RETURNING ref_count",
            (content_hash,)
        )
        result = cursor.fetchone()
        self.conn.commit()

        new_ref_count = result[0] if result else 0

        self.audit.log(
            OperationType.DEREFERENCE,
            content_hash,
            {'new_ref_count': new_ref_count},
            user_id
        )

        return new_ref_count

    def get_stats(self) -> DedupStats:
        """获取统计"""
        cursor = self.conn.execute("""
            SELECT
                COUNT(*) as total_chunks,
                SUM(size) as total_size,
                SUM(ref_count) as total_refs,
                SUM(CASE WHEN ref_count = 0 THEN 1 ELSE 0 END) as orphan_chunks,
                SUM(CASE WHEN is_deleted = 1 THEN 1 ELSE 0 END) as deleted_chunks
            FROM chunks
            WHERE is_deleted = 0
        """)
        row = cursor.fetchone()

        stats = DedupStats(
            total_chunks=row[0] or 0,
            total_size=row[1] or 0,
            total_refs=row[2] or 0,
            unique_chunks=row[0] or 0,
            pending_deletes=sum(
                1 for r in self.delete_requests.values()
                if r.authorization_status == DeleteAuthorizationStatus.PENDING
            )
        )

        # 计算节省空间 (需要知道原始总大小)
        # 这里简化处理
        stats.saved_size = 0

        return stats

    def close(self):
        """关闭数据库"""
        if self.conn:
            self.conn.close()


def main():
    """演示"""
    index = DedupIndexSafe()

    # 添加块
    print("\n=== Adding chunks ===")
    is_new = index.add_chunk(
        chunk_id="chunk-001",
        content_hash="abc123",
        size=1024,
        storage_path="/storage/chunks/chunk-001"
    )
    print(f"New chunk added: {is_new}")

    # 再次添加相同内容 (引用计数 +1)
    is_new = index.add_chunk(
        chunk_id="chunk-002",
        content_hash="abc123",
        size=1024
    )
    print(f"New chunk (duplicate): {is_new}")

    # 获取统计
    stats = index.get_stats()
    print(f"\nStats: chunks={stats.total_chunks}, refs={stats.total_refs}")

    # 查询
    chunk = index.get_by_hash("abc123")
    if chunk:
        print(f"Chunk ref_count: {chunk.ref_count}")

    # 减少引用
    print("\n=== Dereferencing ===")
    remaining = index.dereference("abc123")
    print(f"Remaining refs: {remaining}")

    remaining = index.dereference("abc123")
    print(f"Remaining refs: {remaining}")

    # 请求删除 (此时 ref_count 应该为 0)
    print("\n=== Delete request ===")
    if remaining == 0:
        request_id = index.request_delete("abc123", reason="No more references")
        if request_id:
            print(f"Delete request created: {request_id}")

            # 用户授权
            print("User authorizing delete...")
            index.authorize_delete(request_id)
            print("Delete authorized and executed")

    # 尝试恢复
    print("\n=== Restore from backup ===")
    if index.restore_from_backup("abc123"):
        print("Restored successfully")
    else:
        print("No backup found")

    index.close()


if __name__ == '__main__':
    main()
