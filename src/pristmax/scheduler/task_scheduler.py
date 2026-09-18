"""
M6 Scheduler Module: Task Scheduling and Queue Management

任务调度系统:
- 任务队列管理
- 定时任务
- 优先级调度
- 任务状态追踪
- 失败重试
- Worker 管理

核心原则:
- 后台异步处理
- 任务状态持久化
- 自动重试
- 用户可取消
"""
import os
import sys
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Callable
from pathlib import Path
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"      # 等待中
    QUEUED = "queued"        # 已入队
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0


@dataclass
class Task:
    """任务"""
    task_id: str
    task_type: str  # encode, dedup, scan, etc.
    user_id: str

    # 输入
    input_path: str
    output_path: str = ""

    # 参数
    params: Dict = None  # JSON params

    # 状态
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL

    # 结果
    result: Dict = None
    error: str = ""

    # 进度
    progress: float = 0.0
    progress_message: str = ""

    # 时间
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""

    # 重试
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if self.params is None:
            self.params = {}
        if self.result is None:
            self.result = {}

    def to_dict(self) -> dict:
        d = asdict(self)
        d['status'] = self.status.value
        d['priority'] = self.priority.value
        return d


class ScheduledTask:
    """定时任务"""
    def __init__(
        self,
        task_id: str,
        schedule_type: str,  # "cron", "interval", "once"
        schedule_config: Dict,
        task_params: Dict
    ):
        self.task_id = task_id
        self.schedule_type = schedule_type
        self.schedule_config = schedule_config
        self.task_params = task_params
        self.next_run: Optional[datetime] = None
        self.last_run: Optional[datetime] = None
        self.enabled: bool = True

    def calculate_next_run(self):
        """计算下次执行时间"""
        now = datetime.now()

        if self.schedule_type == "once":
            # 一次性任务
            run_time = self.schedule_config.get("run_at")
            if run_time:
                self.next_run = datetime.fromisoformat(run_time)

        elif self.schedule_type == "interval":
            # 间隔执行
            interval_seconds = self.schedule_config.get("interval_seconds", 3600)
            if self.last_run:
                self.next_run = self.last_run + timedelta(seconds=interval_seconds)
            else:
                self.next_run = now

        elif self.schedule_type == "cron":
            # Cron 表达式简化版 (每日/每周/每月)
            cron_type = self.schedule_config.get("type")  # daily, weekly, monthly
            hour = self.schedule_config.get("hour", 0)
            minute = self.schedule_config.get("minute", 0)

            if cron_type == "daily":
                self.next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if self.next_run < now:
                    self.next_run += timedelta(days=1)

            elif cron_type == "weekly":
                day_of_week = self.schedule_config.get("day_of_week", 0)
                self.next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                days_ahead = (day_of_week - now.weekday()) % 7
                if days_ahead == 0 and self.next_run < now:
                    days_ahead = 7
                self.next_run += timedelta(days=days_ahead)

            elif cron_type == "monthly":
                day_of_month = self.schedule_config.get("day_of_month", 1)
                self.next_run = now.replace(day=day_of_month, hour=hour, minute=minute, second=0, microsecond=0)
                if self.next_run < now:
                    # 下个月
                    if now.month == 12:
                        self.next_run = self.next_run.replace(year=now.year + 1, month=1)
                    else:
                        self.next_run = self.next_run.replace(month=now.month + 1)


class TaskDatabase:
    """任务数据库"""

    def __init__(self, db_path: str = "./tasks.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                user_id TEXT NOT NULL,
                input_path TEXT,
                output_path TEXT,
                params TEXT,
                status TEXT,
                priority INTEGER,
                result TEXT,
                error TEXT,
                progress REAL,
                progress_message TEXT,
                created_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                retry_count INTEGER,
                max_retries INTEGER
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id ON tasks(user_id)
        """)
        self.conn.commit()

    def insert_task(self, task: Task):
        """插入任务"""
        self.conn.execute("""
            INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.task_id,
            task.task_type,
            task.user_id,
            task.input_path,
            task.output_path,
            json.dumps(task.params),
            task.status.value,
            task.priority.value,
            json.dumps(task.result),
            task.error,
            task.progress,
            task.progress_message,
            task.created_at,
            task.started_at,
            task.completed_at,
            task.retry_count,
            task.max_retries
        ))
        self.conn.commit()

    def update_task(self, task: Task):
        """更新任务"""
        self.conn.execute("""
            UPDATE tasks SET
                status = ?,
                progress = ?,
                progress_message = ?,
                result = ?,
                error = ?,
                started_at = ?,
                completed_at = ?,
                retry_count = ?
            WHERE task_id = ?
        """, (
            task.status.value,
            task.progress,
            task.progress_message,
            json.dumps(task.result),
            task.error,
            task.started_at,
            task.completed_at,
            task.retry_count,
            task.task_id
        ))
        self.conn.commit()

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        cursor = self.conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        )
        row = cursor.fetchone()
        return self._row_to_task(row) if row else None

    def get_tasks_by_user(self, user_id: str, status: TaskStatus = None) -> List[Task]:
        """获取用户任务"""
        if status:
            cursor = self.conn.execute(
                "SELECT * FROM tasks WHERE user_id = ? AND status = ? ORDER BY created_at DESC",
                (user_id, status.value)
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
        return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_pending_tasks(self, limit: int = 100) -> List[Task]:
        """获取待处理任务 (按优先级)"""
        cursor = self.conn.execute("""
            SELECT * FROM tasks
            WHERE status IN (?, ?)
            ORDER BY priority ASC, created_at ASC
            LIMIT ?
        """, (TaskStatus.PENDING.value, TaskStatus.QUEUED.value, limit))
        return [self._row_to_task(row) for row in cursor.fetchall()]

    def _row_to_task(self, row) -> Task:
        """行转 Task"""
        return Task(
            task_id=row[0],
            task_type=row[1],
            user_id=row[2],
            input_path=row[3] or "",
            output_path=row[4] or "",
            params=json.loads(row[5]) if row[5] else {},
            status=TaskStatus(row[6]),
            priority=TaskPriority(row[7]),
            result=json.loads(row[8]) if row[8] else {},
            error=row[9] or "",
            progress=row[10] or 0,
            progress_message=row[11] or "",
            created_at=row[12] or "",
            started_at=row[13] or "",
            completed_at=row[14] or "",
            retry_count=row[15] or 0,
            max_retries=row[16] or 3
        )

    def close(self):
        self.conn.close()


class TaskScheduler:
    """
    任务调度器

    功能:
    - 任务提交
    - 优先级队列
    - 定时任务
    - 失败重试
    - 进度追踪
    """

    def __init__(
        self,
        db_path: str = "./tasks.db",
        max_workers: int = 4
    ):
        self.db = TaskDatabase(db_path)
        self.max_workers = max_workers

        # 任务处理器注册
        self.handlers: Dict[str, Callable] = {}

        # 定时任务
        self.scheduled_tasks: Dict[str, ScheduledTask] = {}

        # 运行状态
        self.running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.scheduler_thread: Optional[threading.Thread] = None

        # 执行器
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def register_handler(self, task_type: str, handler: Callable):
        """
        注册任务处理器

        Args:
            task_type: 任务类型 (encode, dedup, scan, etc.)
            handler: 处理函数 (task: Task, progress_callback) -> result
        """
        self.handlers[task_type] = handler

    def submit_task(
        self,
        task_type: str,
        user_id: str,
        input_path: str,
        output_path: str = "",
        params: Dict = None,
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> Task:
        """
        提交任务

        Returns:
            Task
        """
        task_id = f"task-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        task = Task(
            task_id=task_id,
            task_type=task_type,
            user_id=user_id,
            input_path=input_path,
            output_path=output_path,
            params=params or {},
            status=TaskStatus.QUEUED,
            priority=priority,
            created_at=datetime.now().isoformat(),
            max_retries=3
        )

        self.db.insert_task(task)

        print(f"[Scheduler] Task submitted: {task_id} ({task_type})")
        return task

    def cancel_task(self, task_id: str, user_id: str) -> bool:
        """取消任务"""
        task = self.db.get_task(task_id)
        if not task or task.user_id != user_id:
            return False

        if task.status in [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING]:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now().isoformat()
            self.db.update_task(task)
            print(f"[Scheduler] Task cancelled: {task_id}")
            return True

        return False

    def get_task_status(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        return self.db.get_task(task_id)

    def get_user_tasks(self, user_id: str, status: TaskStatus = None) -> List[Task]:
        """获取用户任务"""
        return self.db.get_tasks_by_user(user_id, status)

    def start(self):
        """启动调度器"""
        if self.running:
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.worker_thread.start()
        self.scheduler_thread.start()

        print("[Scheduler] Started")

    def stop(self):
        """停止调度器"""
        self.running = False
        self.executor.shutdown(wait=True)
        print("[Scheduler] Stopped")

    def _worker_loop(self):
        """工作线程循环"""
        while self.running:
            # 获取待处理任务
            tasks = self.db.get_pending_tasks(limit=self.max_workers)

            if not tasks:
                time.sleep(1)
                continue

            # 提交到执行器
            for task in tasks:
                if task.task_type not in self.handlers:
                    task.status = TaskStatus.FAILED
                    task.error = f"No handler for task type: {task.task_type}"
                    self.db.update_task(task)
                    continue

                self.executor.submit(self._execute_task, task)

            time.sleep(0.5)

    def _execute_task(self, task: Task):
        """执行任务"""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now().isoformat()
        self.db.update_task(task)

        print(f"[Scheduler] Executing: {task.task_id}")

        try:
            handler = self.handlers[task.task_type]

            def progress_callback(progress: float, message: str = ""):
                task.progress = progress
                task.progress_message = message
                self.db.update_task(task)

            # 执行
            result = handler(task, progress_callback)

            task.status = TaskStatus.COMPLETED
            task.result = result if result else {}
            task.completed_at = datetime.now().isoformat()
            self.db.update_task(task)

            print(f"[Scheduler] Completed: {task.task_id}")

        except Exception as e:
            task.retry_count += 1
            task.error = str(e)

            if task.retry_count >= task.max_retries:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now().isoformat()
                print(f"[Scheduler] Failed: {task.task_id} (max retries)")
            else:
                task.status = TaskStatus.QUEUED
                print(f"[Scheduler] Retry: {task.task_id} ({task.retry_count}/{task.max_retries})")

            self.db.update_task(task)

        # 发送任务完成/失败通知
        try:
            from src.pristmax.api.task_processor import _notify_task_completion
            _notify_task_completion(task)
        except Exception as e:
            print(f"[Scheduler] Notification error: {e}")

    def _scheduler_loop(self):
        """定时任务调度循环"""
        while self.running:
            now = datetime.now()

            for task_id, scheduled in list(self.scheduled_tasks.items()):
                if not scheduled.enabled:
                    continue

                scheduled.calculate_next_run()

                if scheduled.next_run and scheduled.next_run <= now:
                    # 执行定时任务
                    self.submit_task(
                        task_type="scheduled",
                        user_id="system",
                        input_path="",
                        params=scheduled.task_params
                    )
                    scheduled.last_run = now
                    scheduled.calculate_next_run()

            time.sleep(30)  # 每 30 秒检查一次

    def schedule_task(
        self,
        schedule_type: str,
        schedule_config: Dict,
        task_params: Dict
    ) -> str:
        """创建定时任务"""
        task_id = f"sched-{uuid.uuid4().hex[:8]}"

        scheduled = ScheduledTask(
            task_id=task_id,
            schedule_type=schedule_type,
            schedule_config=schedule_config,
            task_params=task_params
        )
        scheduled.calculate_next_run()

        self.scheduled_tasks[task_id] = scheduled

        print(f"[Scheduler] Scheduled task: {task_id} (next run: {scheduled.next_run})")
        return task_id

    def get_stats(self) -> Dict:
        """获取统计"""
        pending = len(self.db.get_pending_tasks(limit=1000))
        return {
            'total_workers': self.max_workers,
            'pending_tasks': pending,
            'scheduled_tasks': len(self.scheduled_tasks),
            'running': self.running
        }


def main():
    """演示"""
    scheduler = TaskScheduler()

    # 注册处理器
    def encode_handler(task, progress_callback):
        progress_callback(0.0, "Starting...")
        for i in range(10):
            time.sleep(0.1)
            progress_callback((i + 1) * 10, f"Processing {i+1}/10")
        return {'output': task.output_path, 'compression_ratio': 0.35}

    scheduler.register_handler('encode', encode_handler)

    # 启动
    scheduler.start()

    # 提交任务
    task = scheduler.submit_task(
        task_type='encode',
        user_id='user-001',
        input_path='/videos/test.mp4',
        output_path='/videos/test_encoded.mp4',
        priority=TaskPriority.NORMAL
    )

    # 等待完成
    for _ in range(20):
        time.sleep(1)
        task = scheduler.get_task_status(task.task_id)
        if task:
            print(f"Status: {task.status.value}, Progress: {task.progress:.0f}%")
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                break

    scheduler.stop()


if __name__ == '__main__':
    main()
