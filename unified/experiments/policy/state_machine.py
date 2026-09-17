"""
M3 State Machine: File State Management

M3 核心模块: 文件状态机实现。

状态流转:
discovered → encoded → validated → published → retirement_eligible → retired

关键功能:
- 状态转换验证
- 状态历史记录
- 转换回调
- 持久化存储
"""
import json
import uuid
from enum import Enum
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from pathlib import Path


class FileState(Enum):
    """文件状态"""
    DISCOVERED = "discovered"         # 发现
    ENCODED = "encoded"               # 已编码
    VALIDATED = "validated"           # 已验证
    PUBLISHED = "published"           # 已发布
    RETIREMENT_ELIGIBLE = "retirement_eligible"  # 可退休
    RETIRED = "retired"              # 已退休
    FAILED = "failed"                # 失败


class StateTransition:
    """状态转换记录"""
    def __init__(
        self,
        from_state: FileState,
        to_state: FileState,
        reason: str = "",
        metadata: Dict[str, Any] = None
    ):
        self.transition_id = str(uuid.uuid4())[:12]
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        self.metadata = metadata or {}
        self.timestamp = datetime.now().isoformat()


@dataclass
class FileRecord:
    """文件记录"""
    file_id: str
    original_path: str
    current_path: str = ""

    # 状态
    state: FileState = FileState.DISCOVERED
    strategy_id: Optional[str] = None

    # 转换历史
    transitions: List[Dict] = field(default_factory=list)

    # 元数据
    size_bytes: int = 0
    duration_ms: int = 0
    resolution: str = ""
    fps: float = 0.0

    # 质量指标
    psnr: Optional[float] = None
    ssim: Optional[float] = None

    # 策略信息
    original_size: int = 0
    compressed_size: int = 0
    compression_ratio: float = 0.0

    # 时间戳
    discovered_at: str = ""
    encoded_at: Optional[str] = None
    validated_at: Optional[str] = None
    published_at: Optional[str] = None
    retired_at: Optional[str] = None

    # 错误
    error: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> dict:
        result = asdict(self)
        result['state'] = self.state.value
        result['transitions'] = [
            {**t, 'from_state': t['from_state'].value if isinstance(t.get('from_state'), FileState) else t.get('from_state'),
             'to_state': t['to_state'].value if isinstance(t.get('to_state'), FileState) else t.get('to_state')}
            for t in result.get('transitions', [])
        ]
        return result

    @classmethod
    def from_dict(cls, data: dict) -> 'FileRecord':
        if 'state' in data and isinstance(data['state'], str):
            data['state'] = FileState(data['state'])
        # Parse transitions
        if 'transitions' in data:
            for t in data['transitions']:
                if 'from_state' in t and isinstance(t['from_state'], str):
                    t['from_state'] = FileState(t['from_state'])
                if 'to_state' in t and isinstance(t['to_state'], str):
                    t['to_state'] = FileState(t['to_state'])
        return cls(**data)


# 合法的状态转换
VALID_TRANSITIONS: Dict[FileState, List[FileState]] = {
    FileState.DISCOVERED: [FileState.ENCODED, FileState.FAILED],
    FileState.ENCODED: [FileState.VALIDATED, FileState.DISCOVERED, FileState.FAILED],
    FileState.VALIDATED: [FileState.PUBLISHED, FileState.ENCODED, FileState.FAILED],
    FileState.PUBLISHED: [FileState.RETIREMENT_ELIGIBLE, FileState.VALIDATED],
    FileState.RETIREMENT_ELIGIBLE: [FileState.RETIRED, FileState.PUBLISHED],
    FileState.RETIRED: [],  # 终态
    FileState.FAILED: [FileState.DISCOVERED, FileState.ENCODED],  # 可重试
}


class FileStateMachine:
    """
    文件状态机

    管理文件状态流转，支持回调和持久化
    """

    def __init__(self, storage_dir: str = "./state_data"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 文件记录
        self.records: Dict[str, FileRecord] = {}

        # 回调函数
        self.on_state_change: Optional[Callable] = None

        # 加载已保存的记录
        self._load_records()

    def set_state_change_callback(self, callback: Callable):
        """
        设置状态变更回调

        Args:
            callback: (file_id, old_state, new_state, transition) -> None
        """
        self.on_state_change = callback

    def create_file(
        self,
        original_path: str,
        size_bytes: int = 0,
        duration_ms: int = 0,
        resolution: str = "",
        fps: float = 0.0
    ) -> FileRecord:
        """
        创建文件记录

        Args:
            original_path: 原始文件路径
            size_bytes: 文件大小
            duration_ms: 视频时长
            resolution: 分辨率
            fps: 帧率

        Returns:
            FileRecord
        """
        file_id = str(uuid.uuid4())[:12]

        record = FileRecord(
            file_id=file_id,
            original_path=original_path,
            current_path=original_path,
            state=FileState.DISCOVERED,
            size_bytes=size_bytes,
            duration_ms=duration_ms,
            resolution=resolution,
            fps=fps,
            discovered_at=datetime.now().isoformat()
        )

        self.records[file_id] = record
        self._save_record(record)

        print(f"[State] Created: {file_id} -> {original_path}")
        return record

    def transition(
        self,
        file_id: str,
        new_state: FileState,
        reason: str = "",
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        状态转换

        Args:
            file_id: 文件 ID
            new_state: 新状态
            reason: 转换原因
            metadata: 额外元数据

        Returns:
            是否成功
        """
        if file_id not in self.records:
            print(f"[State] File not found: {file_id}")
            return False

        record = self.records[file_id]
        old_state = record.state

        # 验证转换合法性
        if new_state not in VALID_TRANSITIONS.get(old_state, []):
            print(f"[State] Invalid transition: {old_state.value} -> {new_state.value}")
            return False

        # 创建转换记录
        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            reason=reason,
            metadata=metadata or {}
        )

        # 更新记录
        record.state = new_state
        record.transitions.append({
            'transition_id': transition.transition_id,
            'from_state': old_state,
            'to_state': new_state,
            'reason': reason,
            'metadata': metadata or {},
            'timestamp': transition.timestamp
        })

        # 更新特定状态的时间戳
        now = datetime.now().isoformat()
        if new_state == FileState.ENCODED:
            record.encoded_at = now
        elif new_state == FileState.VALIDATED:
            record.validated_at = now
        elif new_state == FileState.PUBLISHED:
            record.published_at = now
        elif new_state == FileState.RETIRED:
            record.retired_at = now

        # 保存
        self._save_record(record)

        # 触发回调
        if self.on_state_change:
            try:
                self.on_state_change(file_id, old_state, new_state, transition)
            except Exception as e:
                print(f"[State] Callback error: {e}")

        print(f"[State] {file_id}: {old_state.value} -> {new_state.value}")
        return True

    def get_file(self, file_id: str) -> Optional[FileRecord]:
        """获取文件记录"""
        return self.records.get(file_id)

    def get_files_by_state(self, state: FileState) -> List[FileRecord]:
        """获取指定状态的文件"""
        return [r for r in self.records.values() if r.state == state]

    def get_history(self, file_id: str) -> List[Dict]:
        """获取状态历史"""
        record = self.records.get(file_id)
        return record.transitions if record else []

    def is_retirement_eligible(self, file_id: str) -> bool:
        """检查文件是否可以退休"""
        record = self.records.get(file_id)
        if not record:
            return False

        # 满足退休条件:
        # 1. 已发布状态
        # 2. 压缩比达标 (至少 20%)
        # 3. 质量达标 (PSNR > 30)
        return (
            record.state == FileState.PUBLISHED and
            record.compression_ratio >= 0.20 and
            (record.psnr is None or record.psnr > 30)
        )

    def mark_retirement_eligible(self, file_id: str) -> bool:
        """标记为可退休"""
        if self.is_retirement_eligible(file_id):
            return self.transition(
                file_id,
                FileState.RETIREMENT_ELIGIBLE,
                reason="compression_qualified"
            )
        return False

    def retire(self, file_id: str) -> bool:
        """退休文件"""
        record = self.records.get(file_id)
        if not record:
            return False

        if record.state != FileState.RETIREMENT_ELIGIBLE:
            print(f"[State] Cannot retire: {file_id} is not retirement_eligible")
            return False

        return self.transition(
            file_id,
            FileState.RETIRED,
            reason="storage_optimization"
        )

    def _save_record(self, record: FileRecord):
        """保存记录"""
        path = self.storage_dir / f"{record.file_id}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)

    def _load_records(self):
        """加载已保存的记录"""
        if not self.storage_dir.exists():
            return

        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    record = FileRecord.from_dict(data)
                    self.records[record.file_id] = record
            except Exception as e:
                print(f"[State] Failed to load {path}: {e}")

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        stats = {state.value: 0 for state in FileState}
        for record in self.records.values():
            stats[record.state.value] += 1
        return stats


def main():
    """演示"""
    sm = FileStateMachine("./state_demo")

    # 创建文件
    file1 = sm.create_file("/path/to/video1.mp4", size_bytes=1000000)
    file2 = sm.create_file("/path/to/video2.mp4", size_bytes=2000000)

    # 状态转换
    sm.transition(file1.file_id, FileState.ENCODED, "encoded_with_roi")
    sm.transition(file1.file_id, FileState.VALIDATED, "quality_passed")
    sm.transition(file1.file_id, FileState.PUBLISHED, "ready_to_serve")

    # 检查统计
    print(f"\n[State] Stats: {sm.get_stats()}")

    # 检查文件
    record = sm.get_file(file1.file_id)
    print(f"[State] File {file1.file_id}: {record.state.value}")


if __name__ == '__main__':
    main()
