"""
M0 Benchmark: Main Orchestrator

基准测试主程序，协调文件收集、编码、验证全流程。
输出机器可读报告和人工可读摘要。

M0 验收标准：
- 同一任务可复查输入、参数、输出和结论
- 任务中断不损坏源数据
- 无法评测的候选不得被接受
"""
import os
import sys
import json
import argparse
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .file_info import FileInfoCollector, MediaInfo
from .encoder import H265Encoder, EncodeResult
from .validator import QualityValidator, QualityMetrics


@dataclass
class BenchmarkTask:
    """基准测试任务"""
    task_id: str
    input_path: str
    output_path: str
    status: str = "pending"  # pending, running, completed, failed
    error: Optional[str] = None

    # 收集的信息
    input_info: Optional[Dict] = None
    encoder_result: Optional[Dict] = None
    quality_metrics: Optional[Dict] = None

    # 时间
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """基准测试报告"""
    report_id: str
    experiment_name: str
    created_at: str

    # 统计
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    # 汇总数据
    total_input_bytes: int = 0
    total_output_bytes: int = 0
    total_encode_time_sec: float = 0.0

    # 质量汇总
    avg_psnr: Optional[float] = None
    min_psnr: Optional[float] = None
    avg_ssim: Optional[float] = None

    # 降量汇总
    total_reduction_ratio: Optional[float] = None
    byte_weighted_reduction: Optional[float] = None

    # 任务详情
    tasks: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class BenchmarkRunner:
    """
    基准测试运行器

    执行流程：
    1. 收集输入文件信息
    2. 执行 H.265 基线编码
    3. 验证输出质量
    4. 生成报告
    """

    def __init__(
        self,
        experiment_name: str,
        output_dir: str,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe"
    ):
        self.experiment_name = experiment_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        self.inputs_dir = self.output_dir / "inputs"
        self.outputs_dir = self.output_dir / "outputs"
        self.reports_dir = self.output_dir / "reports"

        for d in [self.inputs_dir, self.outputs_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 初始化组件
        self.file_collector = FileInfoCollector(ffprobe_path=ffprobe_path)
        self.encoder = H265Encoder(ffmpeg_path=ffmpeg_path)
        self.validator = QualityValidator(
            ffprobe_path=ffprobe_path,
            ffmpeg_path=ffmpeg_path
        )

        # 任务列表
        self.tasks: List[BenchmarkTask] = []
        self.report: Optional[BenchmarkReport] = None

    def add_task(self, input_path: str, preset: str = "medium", crf: int = 28) -> str:
        """
        添加测试任务

        Args:
            input_path: 输入视频路径
            preset: 编码预设
            crf: 质量因子

        Returns:
            str: 任务 ID
        """
        task_id = f"task-{len(self.tasks):03d}"

        # 生成输出路径
        input_name = Path(input_path).stem
        output_name = f"{input_name}_h265_p{preset}_crf{crf}.mp4"
        output_path = str(self.outputs_dir / output_name)

        task = BenchmarkTask(
            task_id=task_id,
            input_path=input_path,
            output_path=output_path,
            created_at=datetime.now().isoformat()
        )

        self.tasks.append(task)
        return task_id

    def run(self, task_id: Optional[str] = None) -> BenchmarkReport:
        """
        运行基准测试

        Args:
            task_id: 可选，指定任务 ID；否则运行所有

        Returns:
            BenchmarkReport: 测试报告
        """
        tasks_to_run = (
            [t for t in self.tasks if t.task_id == task_id]
            if task_id else self.tasks
        )

        print(f"[Benchmark] Starting {len(tasks_to_run)} tasks...")

        for task in tasks_to_run:
            self._run_task(task)

        return self._generate_report()

    def _run_task(self, task: BenchmarkTask):
        """执行单个任务"""
        task.status = "running"
        task.started_at = datetime.now().isoformat()

        print(f"[Benchmark] Running task {task.task_id}: {task.input_path}")

        try:
            # Step 1: 收集输入文件信息
            print(f"  [1/3] Collecting input info...")
            input_info = self.file_collector.collect(task.input_path)
            task.input_info = input_info.to_dict()

            # Step 2: 执行 H.265 编码
            print(f"  [2/3] Encoding with H.265 CRF={input_info.to_dict().get('crf', 28)}...")
            encoder_result = self.encoder.encode(
                task.input_path,
                task.output_path,
                preset="medium",
                crf=28
            )
            task.encoder_result = encoder_result.to_dict()

            if encoder_result.error:
                print(f"  [WARN] Encoder error: {encoder_result.error}")

            # Step 3: 验证输出质量
            print(f"  [3/3] Validating output...")
            quality_metrics = self.validator.validate(
                task.input_path,
                task.output_path,
                calculate_metrics=True
            )
            task.quality_metrics = quality_metrics.to_dict()

            # 更新状态
            if encoder_result.error:
                task.status = "failed"
                task.error = encoder_result.error
            else:
                task.status = "completed"

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            print(f"  [ERROR] Task failed: {e}")

        finally:
            task.completed_at = datetime.now().isoformat()

        print(f"  [DONE] Status: {task.status}")

    def _generate_report(self) -> BenchmarkReport:
        """生成测试报告"""
        completed = [t for t in self.tasks if t.status == "completed"]
        failed = [t for t in self.tasks if t.status == "failed"]

        # 汇总数据
        total_input = sum(t.input_info.get('size_bytes', 0) or 0 for t in completed)
        total_output = sum(t.encoder_result.get('output_size_bytes', 0) or 0 for t in completed)
        total_time = sum(t.encoder_result.get('encode_time_sec', 0) or 0 for t in completed)

        # 计算降量率
        reduction_ratio = None
        byte_weighted = None

        if total_input > 0 and total_output > 0:
            reduction_ratio = 1 - (total_output / total_input)

            # 按字节加权的降量率
            byte_weighted = sum(
                (t.encoder_result.get('reduction_ratio', 0) or 0) *
                t.encoder_result.get('output_size_bytes', 0)
                for t in completed
            ) / total_output if total_output > 0 else None

        # 质量汇总
        psnr_values = [
            t.quality_metrics.get('psnr_avg')
            for t in completed
            if t.quality_metrics and t.quality_metrics.get('psnr_avg')
        ]

        self.report = BenchmarkReport(
            report_id=f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            experiment_name=self.experiment_name,
            created_at=datetime.now().isoformat(),
            total_tasks=len(self.tasks),
            completed_tasks=len(completed),
            failed_tasks=len(failed),
            total_input_bytes=total_input,
            total_output_bytes=total_output,
            total_encode_time_sec=total_time,
            total_reduction_ratio=reduction_ratio,
            byte_weighted_reduction=byte_weighted,
            avg_psnr=sum(psnr_values) / len(psnr_values) if psnr_values else None,
            min_psnr=min(psnr_values) if psnr_values else None,
            tasks=[t.to_dict() for t in self.tasks]
        )

        # 保存报告
        self._save_report()

        return self.report

    def _save_report(self):
        """保存报告到文件"""
        if not self.report:
            return

        report_path = self.reports_dir / f"{self.report.report_id}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.report.to_dict(), f, indent=2, ensure_ascii=False)

        print(f"[Benchmark] Report saved to: {report_path}")

        # 同时打印摘要
        self._print_summary()

    def _print_summary(self):
        """打印摘要"""
        if not self.report:
            return

        r = self.report
        print("\n" + "=" * 60)
        print(f"BENCHMARK REPORT: {r.experiment_name}")
        print("=" * 60)
        print(f"Tasks:        {r.completed_tasks}/{r.total_tasks} completed, {r.failed_tasks} failed")
        print(f"Input:        {self._format_bytes(r.total_input_bytes)}")
        print(f"Output:      {self._format_bytes(r.total_output_bytes)}")

        if r.total_reduction_ratio is not None:
            print(f"Reduction:   {r.total_reduction_ratio * 100:.1f}%")

        if r.byte_weighted_reduction is not None:
            print(f"Byte-weighted: {r.byte_weighted_reduction * 100:.1f}%")

        print(f"Encode time: {r.total_encode_time_sec:.1f} sec")

        if r.avg_psnr is not None:
            print(f"Avg PSNR:    {r.avg_psnr:.2f} dB")

        print("=" * 60)

    def _format_bytes(self, bytes_val: int) -> str:
        """格式化字节大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f} PB"


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='Pristmax M0 基准测试工具 - H.265 重编码基线'
    )

    parser.add_argument(
        'input_files',
        nargs='+',
        help='输入视频文件列表'
    )

    parser.add_argument(
        '--name',
        default='baseline-h265',
        help='实验名称 (默认: baseline-h265)'
    )

    parser.add_argument(
        '--output-dir',
        default='./benchmark_results',
        help='输出目录 (默认: ./benchmark_results)'
    )

    parser.add_argument(
        '--preset',
        default='medium',
        choices=['ultrafast', 'fast', 'medium', 'slow', 'veryslow'],
        help='编码预设 (默认: medium)'
    )

    parser.add_argument(
        '--crf',
        type=int,
        default=28,
        choices=range(0, 52),
        metavar='0-51',
        help='CRF 质量因子 (默认: 28)'
    )

    parser.add_argument(
        '--ffmpeg',
        default='ffmpeg',
        help='FFmpeg 路径'
    )

    parser.add_argument(
        '--ffprobe',
        default='ffprobe',
        help='FFprobe 路径'
    )

    args = parser.parse_args()

    # 创建运行器
    runner = BenchmarkRunner(
        experiment_name=args.name,
        output_dir=args.output_dir,
        ffmpeg_path=args.ffmpeg,
        ffprobe_path=args.ffprobe
    )

    # 添加任务
    for input_file in args.input_files:
        if not os.path.exists(input_file):
            print(f"[WARN] File not found: {input_file}, skipping...")
            continue
        runner.add_task(input_file, preset=args.preset, crf=args.crf)

    if not runner.tasks:
        print("[ERROR] No valid input files")
        return 1

    # 运行
    report = runner.run()

    # 打印结果
    if report.failed_tasks == 0:
        print("\n[PASS] All tasks completed successfully")
        return 0
    else:
        print(f"\n[FAIL] {report.failed_tasks} tasks failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
