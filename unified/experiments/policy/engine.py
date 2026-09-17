"""
M3 Policy Engine: Strategy Plugin System

M3 核心模块: 将实验算法接为可禁用的策略插件。

策略状态机:
discovered → encoded → validated → published → retirement_eligible → retired

关键功能:
- 策略注册与启用/禁用
- 任务队列管理
- 幂等重试
- 故障恢复
- 质量失败回退
"""
import json
import uuid
import time
from enum import Enum
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from pathlib import Path


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    VALIDATING = "validating"
    PUBLISHED = "published"
    RETIREMENT_ELIGIBLE = "retirement_eligible"
    RETIRED = "retired"
    FAILED = "failed"
    RETRY = "retry"


class StrategyType(Enum):
    """策略类型"""
    ROI_BLUR = "roi_blur"           # M1: ROI + 背景模糊
    ASVC = "asvc"                   # M2: ASVC
    BLUE = "blue"                   # M2: BLUE
    BASELINE = "baseline"            # H.265 基线
    CUSTOM = "custom"               # 自定义


@dataclass
class Strategy:
    """策略定义"""
    strategy_id: str
    name: str
    strategy_type: StrategyType
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)

    # 策略参数
    crf: int = 28
    preset: str = "medium"
    motion_threshold: int = 25
    blur_kernel: int = 21

    # 质量门槛
    min_psnr: float = 30.0
    min_ssim: float = 0.90

    def to_dict(self) -> dict:
        result = asdict(self)
        result['strategy_type'] = self.strategy_type.value
        return result


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    strategy_id: str
    status: TaskStatus

    # 输入输出
    input_path: str = ""
    output_path: str = ""
    original_size: int = 0
    compressed_size: int = 0

    # 质量指标
    psnr: Optional[float] = None
    ssim: Optional[float] = None

    # 错误
    error: Optional[str] = None
    retry_count: int = 0
    failure_reason: Optional[str] = None

    # 时间
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        result = asdict(self)
        result['status'] = self.status.value
        return result


class PolicyEngine:
    """
    策略引擎

    管理策略注册、任务队列、执行控制
    """

    def __init__(self, storage_dir: str = "./policy_data"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 策略注册表
        self.strategies: Dict[str, Strategy] = {}

        # 任务队列
        self.task_queue: List[str] = []  # task_id 列表
        self.task_results: Dict[str, TaskResult] = {}

        # 回调函数
        self.processors: Dict[StrategyType, Callable] = {}

        # 加载已保存的策略
        self._load_strategies()

    def register_strategy(self, strategy: Strategy) -> str:
        """
        注册策略

        Args:
            strategy: 策略定义

        Returns:
            strategy_id
        """
        if not strategy.strategy_id:
            strategy.strategy_id = f"strategy-{uuid.uuid4().hex[:8]}"

        self.strategies[strategy.strategy_id] = strategy
        self._save_strategy(strategy)

        print(f"[Policy] Registered: {strategy.name} ({strategy.strategy_id})")
        return strategy.strategy_id

    def enable_strategy(self, strategy_id: str) -> bool:
        """启用策略"""
        if strategy_id not in self.strategies:
            return False
        self.strategies[strategy_id].enabled = True
        self._save_strategy(self.strategies[strategy_id])
        return True

    def disable_strategy(self, strategy_id: str) -> bool:
        """禁用策略"""
        if strategy_id not in self.strategies:
            return False
        self.strategies[strategy_id].enabled = False
        self._save_strategy(self.strategies[strategy_id])
        return True

    def register_processor(self, strategy_type: StrategyType, processor: Callable):
        """
        注册策略处理器

        Args:
            strategy_type: 策略类型
            processor: 处理函数 (input_path, output_path, config) -> TaskResult
        """
        self.processors[strategy_type] = processor

    def submit_task(
        self,
        strategy_id: str,
        input_path: str,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        提交任务

        Args:
            strategy_id: 策略 ID
            input_path: 输入文件路径
            output_path: 输出路径 (可选)

        Returns:
            task_id 或 None
        """
        if strategy_id not in self.strategies:
            print(f"[Policy] Strategy not found: {strategy_id}")
            return None

        strategy = self.strategies[strategy_id]
        if not strategy.enabled:
            print(f"[Policy] Strategy disabled: {strategy_id}")
            return None

        # 生成任务 ID
        task_id = f"task-{uuid.uuid4().hex[:12]}"

        # 创建任务结果
        task = TaskResult(
            task_id=task_id,
            strategy_id=strategy_id,
            status=TaskStatus.PENDING,
            input_path=input_path,
            output_path=output_path or self._generate_output_path(input_path),
            created_at=datetime.now().isoformat()
        )

        self.task_results[task_id] = task
        self.task_queue.append(task_id)

        print(f"[Policy] Task submitted: {task_id} ({strategy.name})")
        return task_id

    def execute_task(self, task_id: str) -> TaskResult:
        """
        执行任务

        Args:
            task_id: 任务 ID

        Returns:
            TaskResult
        """
        if task_id not in self.task_results:
            raise ValueError(f"Task not found: {task_id}")

        task = self.task_results[task_id]
        strategy = self.strategies.get(task.strategy_id)

        if not strategy:
            task.status = TaskStatus.FAILED
            task.error = f"Strategy not found: {task.strategy_id}"
            return task

        # 检查是否有处理器
        if strategy.strategy_type not in self.processors:
            task.status = TaskStatus.FAILED
            task.error = f"No processor for strategy type: {strategy.strategy_type.value}"
            return task

        # 更新状态
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now().isoformat()

        try:
            # 获取处理器
            processor = self.processors[strategy.strategy_type]

            # 执行处理
            result = processor(
                task.input_path,
                task.output_path,
                strategy.config
            )

            # 更新结果
            if isinstance(result, TaskResult):
                task = result
            else:
                task.compressed_size = result.get('compressed_size', 0)
                task.psnr = result.get('psnr')
                task.ssim = result.get('ssim')

            # 质量检查
            if strategy.min_psnr and task.psnr and task.psnr < strategy.min_psnr:
                task.status = TaskStatus.FAILED
                task.failure_reason = f"PSNR {task.psnr:.2f} < {strategy.min_psnr}"
                return task

            if strategy.min_ssim and task.ssim and task.ssim < strategy.min_ssim:
                task.status = TaskStatus.FAILED
                task.failure_reason = f"SSIM {task.ssim:.4f} < {strategy.min_ssim}"
                return task

            # 成功
            task.status = TaskStatus.VALIDATED
            task.completed_at = datetime.now().isoformat()

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.retry_count += 1

        # 保存任务结果
        self._save_task_result(task)

        return task

    def retry_task(self, task_id: str) -> TaskResult:
        """重试任务"""
        if task_id not in self.task_results:
            raise ValueError(f"Task not found: {task_id}")

        task = self.task_results[task_id]

        if task.retry_count >= 3:
            task.status = TaskStatus.FAILED
            task.failure_reason = "Max retries exceeded"
            return task

        task.status = TaskStatus.RETRY
        self.task_queue.append(task_id)

        return self.execute_task(task_id)

    def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        """获取任务状态"""
        return self.task_results.get(task_id)

    def list_strategies(self) -> List[Strategy]:
        """列出所有策略"""
        return list(self.strategies.values())

    def list_pending_tasks(self) -> List[TaskResult]:
        """列出待处理任务"""
        return [
            self.task_results[tid]
            for tid in self.task_queue
            if tid in self.task_results
        ]

    def _generate_output_path(self, input_path: str) -> str:
        """生成输出路径"""
        p = Path(input_path)
        stem = p.stem
        suffix = p.suffix
        output_dir = self.storage_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / f"{stem}_processed{suffix}")

    def _save_strategy(self, strategy: Strategy):
        """保存策略到磁盘"""
        path = self.storage_dir / "strategies" / f"{strategy.strategy_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(strategy.to_dict(), f, indent=2)

    def _save_task_result(self, task: TaskResult):
        """保存任务结果"""
        path = self.storage_dir / "tasks" / f"{task.task_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(task.to_dict(), f, indent=2)

    def _load_strategies(self):
        """加载已保存的策略"""
        strategies_dir = self.storage_dir / "strategies"
        if not strategies_dir.exists():
            return

        for path in strategies_dir.glob("*.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    data['strategy_type'] = StrategyType(data['strategy_type'])
                    strategy = Strategy(**data)
                    self.strategies[strategy.strategy_id] = strategy
            except Exception as e:
                print(f"[Policy] Failed to load strategy {path}: {e}")


def create_default_strategies() -> List[Strategy]:
    """创建默认策略"""
    return [
        Strategy(
            strategy_id="roi-blur-01",
            name="ROI + 背景模糊",
            strategy_type=StrategyType.ROI_BLUR,
            enabled=True,
            config={
                'crf': 28,
                'blur_kernel': 21,
                'motion_threshold': 25
            }
        ),
        Strategy(
            strategy_id="asvc-01",
            name="ASVC 背景差分",
            strategy_type=StrategyType.ASVC,
            enabled=False,
            config={
                'crf': 28,
                'gop_size': 12
            }
        ),
        Strategy(
            strategy_id="blue-01",
            name="BLUE 背景冻结",
            strategy_type=StrategyType.BLUE,
            enabled=False,
            config={
                'crf': 28,
                'seed_interval': 30
            }
        ),
        Strategy(
            strategy_id="baseline-h265",
            name="H.265 基线",
            strategy_type=StrategyType.BASELINE,
            enabled=True,
            config={
                'crf': 28,
                'preset': 'medium'
            }
        ),
    ]


def main():
    """演示"""
    engine = PolicyEngine("./policy_demo")

    # 注册默认策略
    for strategy in create_default_strategies():
        engine.register_strategy(strategy)

    # 列出策略
    print("\n[Policy] Registered strategies:")
    for s in engine.list_strategies():
        print(f"  - {s.name} ({s.strategy_type.value}) enabled={s.enabled}")


if __name__ == '__main__':
    main()
