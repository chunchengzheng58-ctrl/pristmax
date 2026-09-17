"""
M3 Task Queue: Resource Management and Retry Logic

M3 核心模块: 任务队列管理。

关键功能:
- 任务优先级队列
- 资源限制 (CPU/内存/并发)
- 幂等重试
- 死信队列
"""
import uuid
import time
import threading
from enum import Enum
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from queue import PriorityQueue, Empty
from pathlib import Path


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    CRITICAL = 0


class TaskState(Enum):
    """队列任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueuedTask:
    """队列任务"""
    task_id: str
    priority: TaskPriority
    strategy_id: str
    input_path: str
    output_path: str = ""

    state: TaskState = TaskState.PENDING
    retry_count: int = 0
    max_retries: int = 3

    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    error: Optional[str] = None

    # 用于优先级队列排序
    def __lt__(self, other):
        return self.priority.value < other.priority.value

    def to_dict(self) -> dict:
        return asdict(self)


class ResourceLimit:
    """资源限制"""
    def __init__(
        self,
        max_concurrent: int = 2,
        max_memory_mb: int = 2048,
        max_cpu_percent: int = 80
    ):
        self.max_concurrent = max_concurrent
        self.max_memory_mb = max_memory_mb
        self.max_cpu_percent = max_cpu_percent

        self._active_count = 0
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        """获取资源"""
        with self._lock:
            if self._active_count < self.max_concurrent:
                self._active_count += 1
                return True
            return False

    def release(self):
        """释放资源"""
        with self._lock:
            self._active_count = max(0, self._active_count - 1)

    @property
    def available(self) -> int:
        """可用并发数"""
        with self._lock:
            return max(0, self.max_concurrent - self._active_count)


class TaskQueue:
    """
    任务队列

    支持优先级、资源限制、幂等重试
    """

    def __init__(
        self,
        storage_dir: str = "./queue_data",
        resource_limit: ResourceLimit = None
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 队列
        self.queue: PriorityQueue = PriorityQueue()
        self.tasks: Dict[str, QueuedTask] = {}

        # 死信队列 (重试超过上限的任务)
        self.dead_letter: List[QueuedTask] = []

        # 资源限制
        self.resource_limit = resource_limit or ResourceLimit()

        # 处理器
        self.processor: Optional[Callable] = None

        # 运行状态
        self.running = False
        self.worker_thread: Optional[threading.Thread] = None

    def set_processor(self, processor: Callable):
        """
        设置任务处理器

        Args:
            processor: (task: QueuedTask) -> bool
                      返回 True 表示成功，False 表示失败
        """
        self.processor = processor

    def enqueue(
        self,
        strategy_id: str,
        input_path: str,
        output_path: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        task_id: str = None
    ) -> str:
        """
        入队任务

        Args:
            strategy_id: 策略 ID
            input_path: 输入路径
            output_path: 输出路径
            priority: 优先级
            max_retries: 最大重试次数
            task_id: 可选的预定义任务 ID (用于幂等)

        Returns:
            task_id
        """
        # 幂等检查: 如果任务已存在，返回现有 ID
        if task_id and task_id in self.tasks:
            existing = self.tasks[task_id]
            if existing.state in [TaskState.PENDING, TaskState.RUNNING]:
                print(f"[Queue] Task already exists: {task_id}")
                return task_id

        task_id = task_id or f"q-{uuid.uuid4().hex[:12]}"

        task = QueuedTask(
            task_id=task_id,
            priority=priority,
            strategy_id=strategy_id,
            input_path=input_path,
            output_path=output_path,
            max_retries=max_retries,
            created_at=datetime.now().isoformat()
        )

        self.tasks[task_id] = task
        self.queue.put(task)
        self._save_task(task)

        print(f"[Queue] Enqueued: {task_id} ({priority.name})")
        return task_id

    def start(self):
        """启动队列处理器"""
        if self.running:
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

        print("[Queue] Started")

    def stop(self):
        """停止队列处理器"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        print("[Queue] Stopped")

    def _worker(self):
        """工作线程"""
        while self.running:
            try:
                # 等待任务
                task = self.queue.get(timeout=1)

                # 检查资源
                if not self.resource_limit.acquire():
                    # 资源不足，放回队列
                    self.queue.put(task)
                    time.sleep(1)
                    continue

                # 处理任务
                self._process_task(task)

                # 释放资源
                self.resource_limit.release()

            except Empty:
                continue
            except Exception as e:
                print(f"[Queue] Worker error: {e}")

    def _process_task(self, task: QueuedTask):
        """处理单个任务"""
        task.state = TaskState.RUNNING
        task.started_at = datetime.now().isoformat()
        self._save_task(task)

        print(f"[Queue] Processing: {task.task_id}")

        try:
            if self.processor:
                success = self.processor(task)
            else:
                success = False

            if success:
                task.state = TaskState.COMPLETED
                print(f"[Queue] Completed: {task.task_id}")
            else:
                task.state = TaskState.FAILED
                task.error = "Processing failed"
                self._handle_failure(task)

        except Exception as e:
            task.state = TaskState.FAILED
            task.error = str(e)
            self._handle_failure(task)

        task.completed_at = datetime.now().isoformat()
        self._save_task(task)

    def _handle_failure(self, task: QueuedTask):
        """处理失败"""
        task.retry_count += 1

        if task.retry_count < task.max_retries:
            # 重试
            print(f"[Queue] Retrying: {task.task_id} ({task.retry_count}/{task.max_retries})")
            task.state = TaskState.PENDING
            self.queue.put(task)
        else:
            # 死信
            print(f"[Queue] Dead letter: {task.task_id}")
            self.dead_letter.append(task)

    def get_task(self, task_id: str) -> Optional[QueuedTask]:
        """获取任务"""
        return self.tasks.get(task_id)

    def get_pending_tasks(self) -> List[QueuedTask]:
        """获取待处理任务"""
        return [
            t for t in self.tasks.values()
            if t.state == TaskState.PENDING
        ]

    def get_running_tasks(self) -> List[QueuedTask]:
        """获取运行中任务"""
        return [
            t for t in self.tasks.values()
            if t.state == TaskState.RUNNING
        ]

    def get_dead_letters(self) -> List[QueuedTask]:
        """获取死信队列"""
        return self.dead_letter

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.state in [TaskState.PENDING, TaskState.RUNNING]:
            task.state = TaskState.CANCELLED
            self._save_task(task)
            return True

        return False

    def _save_task(self, task: QueuedTask):
        """保存任务状态"""
        path = self.storage_dir / f"{task.task_id}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(task.to_dict(), f, indent=2)

    def _load_tasks(self):
        """加载任务"""
        if not self.storage_dir.exists():
            return

        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    task = QueuedTask(**data)
                    self.tasks[task.task_id] = task
            except Exception as e:
                print(f"[Queue] Failed to load {path}: {e}")

    def get_stats(self) -> Dict[str, int]:
        """获取统计"""
        return {
            'total': len(self.tasks),
            'pending': len(self.get_pending_tasks()),
            'running': len(self.get_running_tasks()),
            'completed': sum(1 for t in self.tasks.values() if t.state == TaskState.COMPLETED),
            'failed': sum(1 for t in self.tasks.values() if t.state == TaskState.FAILED),
            'dead_letter': len(self.dead_letter)
        }


# JSON 序列化支持
import json

def _dataclass_to_json(obj):
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()
    return obj.__dict__

# 扩展 json 支持
json.JSONEncoder.default = lambda self, obj: _dataclass_to_json(obj)


def main():
    """演示"""
    queue = TaskQueue("./queue_demo")

    # 入队
    queue.enqueue("roi-blur-01", "/video1.mp4", priority=TaskPriority.NORMAL)
    queue.enqueue("asvc-01", "/video2.mp4", priority=TaskPriority.HIGH)

    print(f"[Queue] Stats: {queue.get_stats()}")


if __name__ == '__main__':
    main()
