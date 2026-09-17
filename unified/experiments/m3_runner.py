"""
M3 Runner: Enterprise Policy Integration

M3 主程序: 集成策略引擎、状态机、任务队列和存储连接器。

状态流转:
discovered → encoded → validated → published → retirement_eligible → retired

功能:
- 策略插件管理
- 任务队列处理
- 状态机管理
- 存储连接器集成
"""
import os
import sys
import json
import argparse
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from .policy import (
    PolicyEngine,
    Strategy,
    StrategyType,
    TaskStatus,
    FileStateMachine,
    FileState,
    TaskQueue,
    TaskPriority,
    ResourceLimit,
    create_default_strategies
)

from .storage import (
    LocalConnector,
    ConnectorFactory
)


@dataclass
class M3Report:
    """M3 实验报告"""
    report_id: str
    experiment_name: str
    created_at: str

    # 策略统计
    total_strategies: int = 0
    enabled_strategies: int = 0

    # 任务统计
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    # 状态统计
    state_stats: Dict[str, int] = None

    # 存储统计
    storage_stats: Dict[str, Any] = None

    def __post_init__(self):
        if self.state_stats is None:
            self.state_stats = {}
        if self.storage_stats is None:
            self.storage_stats = {}

    def to_dict(self) -> dict:
        return asdict(self)


class M3Runner:
    """
    M3 企业策略集成运行器

    集成流程:
    1. 初始化策略引擎
    2. 初始化状态机
    3. 初始化任务队列
    4. 初始化存储连接器
    5. 注册策略处理器
    6. 扫描并处理文件
    """

    def __init__(
        self,
        experiment_name: str,
        storage_path: str,
        output_dir: str = "./m3_results"
    ):
        self.experiment_name = experiment_name
        self.storage_path = storage_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化组件
        self.policy_engine = PolicyEngine(str(self.output_dir / "policy"))
        self.state_machine = FileStateMachine(str(self.output_dir / "state"))
        self.task_queue = TaskQueue(
            str(self.output_dir / "queue"),
            ResourceLimit(max_concurrent=2)
        )
        self.storage = LocalConnector(storage_path)

        # 注册默认策略
        for strategy in create_default_strategies():
            self.policy_engine.register_strategy(strategy)

        # 连接存储
        self.storage.connect()

        # 注册状态变更回调
        self.state_machine.set_state_change_callback(self._on_state_change)

        # 注册任务处理器
        self.task_queue.set_processor(self._process_task)

    def _on_state_change(self, file_id: str, old_state: FileState, new_state: FileState, transition):
        """状态变更回调"""
        print(f"[M3] State change: {file_id} {old_state.value} -> {new_state.value}")

        # 可以在这里添加通知、审计等逻辑
        if new_state == FileState.RETIREMENT_ELIGIBLE:
            print(f"[M3] File eligible for retirement: {file_id}")

    def _process_task(self, task) -> bool:
        """
        处理任务

        Args:
            task: QueuedTask

        Returns:
            是否成功
        """
        try:
            # 获取策略
            strategy = self.policy_engine.strategies.get(task.strategy_id)
            if not strategy:
                print(f"[M3] Strategy not found: {task.strategy_id}")
                return False

            # 获取文件记录
            record = self.state_machine.records.get(task.input_path)
            if not record:
                # 创建新记录
                record = self.state_machine.create_file(task.input_path)

            # 执行状态转换
            self.state_machine.transition(
                record.file_id,
                FileState.ENCODED,
                reason=f"strategy:{strategy.name}"
            )

            # 模拟处理 (实际应调用编码器)
            import time
            time.sleep(0.1)  # 模拟处理

            # 更新记录
            record.compressed_size = record.size_bytes * 0.7  # 模拟压缩
            record.compression_ratio = 0.3
            record.psnr = 35.0

            # 验证通过
            self.state_machine.transition(
                record.file_id,
                FileState.VALIDATED,
                reason="quality_passed"
            )

            self.state_machine.transition(
                record.file_id,
                FileState.PUBLISHED,
                reason="ready_to_serve"
            )

            # 检查是否可以退休
            if self.state_machine.is_retirement_eligible(record.file_id):
                self.state_machine.mark_retirement_eligible(record.file_id)

            return True

        except Exception as e:
            print(f"[M3] Task failed: {e}")
            return False

    def scan_storage(self, extensions: List[str] = None) -> List[str]:
        """
        扫描存储

        Args:
            extensions: 文件扩展名列表，如 ['.mp4', '.avi']

        Returns:
            文件路径列表
        """
        if extensions is None:
            extensions = ['.mp4', '.avi', '.mkv', '.mov']

        files = []
        for root, dirs, filenames in os.walk(self.storage_path):
            for filename in filenames:
                if any(filename.lower().endswith(ext) for ext in extensions):
                    files.append(os.path.join(root, filename))

        print(f"[M3] Scanned {len(files)} video files")
        return files

    def process_files(self, file_paths: List[str], strategy_id: str = "roi-blur-01"):
        """
        处理文件

        Args:
            file_paths: 文件路径列表
            strategy_id: 策略 ID
        """
        for path in file_paths:
            self.task_queue.enqueue(
                strategy_id=strategy_id,
                input_path=path,
                priority=TaskPriority.NORMAL
            )

        print(f"[M3] Enqueued {len(file_paths)} tasks")

    def start(self):
        """启动任务队列"""
        self.task_queue.start()
        print("[M3] Task queue started")

    def stop(self):
        """停止任务队列"""
        self.task_queue.stop()
        print("[M3] Task queue stopped")

    def generate_report(self) -> M3Report:
        """生成报告"""
        report = M3Report(
            report_id=f"m3-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            experiment_name=self.experiment_name,
            created_at=datetime.now().isoformat()
        )

        # 策略统计
        strategies = self.policy_engine.list_strategies()
        report.total_strategies = len(strategies)
        report.enabled_strategies = sum(1 for s in strategies if s.enabled)

        # 任务统计
        queue_stats = self.task_queue.get_stats()
        report.total_tasks = queue_stats['total']
        report.completed_tasks = queue_stats['completed']
        report.failed_tasks = queue_stats['failed']

        # 状态统计
        report.state_stats = self.state_machine.get_stats()

        # 存储统计
        storage_stats = self.storage.get_stats()
        report.storage_stats = {
            'total_gb': storage_stats.total_bytes / 1024**3,
            'used_gb': storage_stats.used_bytes / 1024**3,
            'available_gb': storage_stats.available_bytes / 1024**3,
            'usage_percent': storage_stats.usage_percent()
        }

        # 保存报告
        report_path = self.output_dir / "reports" / f"{report.report_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        self._print_summary(report)

        return report

    def _print_summary(self, report: M3Report):
        """打印摘要"""
        print("\n" + "=" * 70)
        print(f"M3 ENTERPRISE REPORT: {report.experiment_name}")
        print("=" * 70)
        print(f"\nStrategies:")
        print(f"  Total: {report.total_strategies}")
        print(f"  Enabled: {report.enabled_strategies}")

        print(f"\nTasks:")
        print(f"  Total: {report.total_tasks}")
        print(f"  Completed: {report.completed_tasks}")
        print(f"  Failed: {report.failed_tasks}")

        print(f"\nFile States:")
        for state, count in report.state_stats.items():
            print(f"  {state}: {count}")

        print(f"\nStorage:")
        print(f"  Usage: {report.storage_stats['usage_percent']:.1f}%")
        print(f"  Available: {report.storage_stats['available_gb']:.1f} GB")
        print("=" * 70)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='M3: 企业策略集成')

    parser.add_argument('--storage', default='./test_videos', help='存储路径')
    parser.add_argument('--output-dir', default='./m3_results', help='输出目录')
    parser.add_argument('--name', default='m3-experiment', help='实验名称')
    parser.add_argument('--scan-only', action='store_true', help='仅扫描不处理')

    args = parser.parse_args()

    runner = M3Runner(
        experiment_name=args.name,
        storage_path=args.storage,
        output_dir=args.output_dir
    )

    # 扫描文件
    files = runner.scan_storage()
    print(f"\n[M3] Found {len(files)} files")

    if args.scan_only:
        return 0

    if files:
        # 处理文件
        runner.process_files(files[:10])  # 限制处理数量
        runner.start()

        # 等待处理
        import time
        try:
            while True:
                stats = runner.task_queue.get_stats()
                if stats['pending'] == 0 and stats['running'] == 0:
                    break
                print(f"[M3] Progress: {stats['completed']}/{stats['total']}")
                time.sleep(2)
        except KeyboardInterrupt:
            pass

        runner.stop()

    # 生成报告
    report = runner.generate_report()

    return 0


if __name__ == '__main__':
    sys.exit(main())
