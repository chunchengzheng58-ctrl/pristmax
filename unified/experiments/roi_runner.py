"""
M1 Runner: ROI Processing Batch Runner

M1 主程序: 批量执行 ROI 编码任务，生成可对比的实验报告。

M1 验收标准:
- 相对同配置普通编码器存在额外收益
- 客户选定的关键任务质量通过
- 任一硬门槛失败则保留基线候选或原件，并说明原因
- 普通重编码节省不得归功于 ROI 算法
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
sys.path.insert(0, str(Path(__file__).parent))

from .benchmark import BenchmarkRunner
from .roi import ROIEncoder, ROIEncoderConfig, ROIEncoderResult


@dataclass
class M1Report:
    """M1 实验报告"""
    report_id: str
    experiment_name: str
    created_at: str

    # 任务统计
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    conservative_tasks: int = 0
    fallback_tasks: int = 0

    # 汇总数据
    total_input_bytes: int = 0
    total_baseline_bytes: int = 0
    total_roi_bytes: int = 0

    # 降量汇总
    baseline_reduction_avg: float = 0.0  # 基线平均降量率
    roi_reduction_avg: float = 0.0  # ROI 平均降量率
    incremental_gain_avg: float = 0.0  # 平均增量收益

    # 增量收益为正的任务比例
    positive_gain_ratio: float = 0.0

    # 质量汇总
    avg_psnr: Optional[float] = None
    min_psnr: Optional[float] = None

    # ROI 检测汇总
    avg_roi_ratio: float = 0.0
    avg_motion_ratio: float = 0.0
    scenes_with_stationary_objects: int = 0

    # 任务详情
    tasks: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        # 计算节省空间
        if self.total_input_bytes > 0:
            result['total_saved_bytes'] = self.total_input_bytes - self.total_roi_bytes
            result['total_saved_percent'] = (
                (self.total_input_bytes - self.total_roi_bytes) / self.total_input_bytes * 100
            )
        return result


class M1Runner:
    """
    M1 ROI 批量处理运行器

    对比实验:
    1. 原始视频 → H.265 基线
    2. 原始视频 → ROI 检测 → 背景模糊 → H.265

    输出:
    - 每个任务的详细结果
    - 对比报告 (基线 vs ROI)
    - 可追溯的实验记录
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
        self.baseline_dir = self.output_dir / "baseline"
        self.roi_dir = self.output_dir / "roi"
        self.reports_dir = self.output_dir / "reports"

        for d in [self.baseline_dir, self.roi_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

        # 任务列表
        self.tasks: List[ROIEncoderResult] = []
        self.report: Optional[M1Report] = None

    def add_task(
        self,
        input_path: str,
        crf: int = 28,
        preset: str = "medium",
        motion_threshold: int = 25,
        blur_kernel: int = 21
    ) -> str:
        """
        添加 ROI 编码任务

        Args:
            input_path: 输入视频路径
            crf: 质量因子
            preset: 编码预设
            motion_threshold: 运动检测阈值
            blur_kernel: 模糊核大小

        Returns:
            str: 任务 ID
        """
        task_id = f"m1-task-{len(self.tasks):03d}"

        config = ROIEncoderConfig(
            motion_threshold=motion_threshold,
            blur_kernel=blur_kernel,
            h265_crf=crf,
            h265_preset=preset
        )

        encoder = ROIEncoder(
            config=config,
            ffmpeg_path=self.ffmpeg_path,
            ffprobe_path=self.ffprobe_path
        )

        # 临时存储编码器用于后续执行
        task_data = {
            'task_id': task_id,
            'input_path': input_path,
            'config': config,
            'encoder': encoder
        }

        self.tasks.append(task_data)
        return task_id

    def run(self, task_id: Optional[str] = None) -> M1Report:
        """
        运行所有任务

        Args:
            task_id: 可选，指定任务 ID

        Returns:
            M1Report: 实验报告
        """
        tasks_to_run = (
            [t for t in self.tasks if t['task_id'] == task_id]
            if task_id else self.tasks
        )

        print(f"[M1] Starting {len(tasks_to_run)} tasks...")

        completed_tasks = []

        for task_data in tasks_to_run:
            print(f"\n[M1] Running task {task_data['task_id']}: {task_data['input_path']}")

            result = self._run_task(task_data)
            completed_tasks.append(result)

        return self._generate_report(completed_tasks)

    def _run_task(self, task_data: Dict) -> ROIEncoderResult:
        """执行单个任务"""
        input_path = task_data['input_path']
        config = task_data['config']
        encoder = task_data['encoder']

        # 基线输出路径
        baseline_output = self.baseline_dir / f"{Path(input_path).stem}_baseline_crf{config.h265_crf}.mp4"

        # ROI 输出目录
        roi_output = self.roi_dir

        # 执行 ROI 编码
        result = encoder.encode(
            input_path=input_path,
            output_dir=str(roi_output),
            baseline_output_path=str(baseline_output),
            task_id=task_data['task_id']
        )

        # 保存基线结果引用
        result.baseline_size_bytes = config.h265_crf  # 临时存储，用于报告

        print(f"[M1] Task {task_data['task_id']} completed: {result.status}")
        print(f"[M1]   Mode: {result.processing_mode}")
        print(f"[M1]   ROI ratio: {result.roi_ratio:.2%}")
        print(f"[M1]   Incremental gain: {result.incremental_gain:+.2%}")

        return result

    def _generate_report(self, completed_tasks: List[ROIEncoderResult]) -> M1Report:
        """生成实验报告"""

        total = len(completed_tasks)
        completed = sum(1 for t in completed_tasks if t.status == "completed")
        failed = total - completed
        conservative = sum(1 for t in completed_tasks if t.processing_mode == "conservative")
        fallback = sum(1 for t in completed_tasks if t.processing_mode == "fallback_baseline")

        # 汇总数据
        total_input = sum(t.input_size_bytes for t in completed_tasks)
        total_baseline = sum(t.baseline_size_bytes for t in completed_tasks if t.baseline_size_bytes > 0)
        total_roi = sum(t.encoded_size_bytes for t in completed_tasks)

        # 计算平均降量率
        baseline_reductions = [
            1 - (t.baseline_size_bytes / t.input_size_bytes)
            for t in completed_tasks
            if t.input_size_bytes > 0 and t.baseline_size_bytes > 0
        ]

        roi_reductions = [
            1 - (t.encoded_size_bytes / t.input_size_bytes)
            for t in completed_tasks
            if t.input_size_bytes > 0 and t.encoded_size_bytes > 0
        ]

        incremental_gains = [t.incremental_gain for t in completed_tasks]

        positive_gains = sum(1 for g in incremental_gains if g > 0)

        # 质量汇总
        psnr_values = [
            t.quality_metrics.get('psnr_avg')
            for t in completed_tasks
            if t.quality_metrics and t.quality_metrics.get('psnr_avg')
        ]

        # ROI 检测汇总
        roi_ratios = [t.roi_ratio for t in completed_tasks if t.roi_ratio > 0]
        motion_ratios = [t.motion_ratio for t in completed_tasks if t.motion_ratio > 0]
        stationary_count = sum(1 for t in completed_tasks if t.has_stationary_objects)

        self.report = M1Report(
            report_id=f"m1-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            experiment_name=self.experiment_name,
            created_at=datetime.now().isoformat(),
            total_tasks=total,
            completed_tasks=completed,
            failed_tasks=failed,
            conservative_tasks=conservative,
            fallback_tasks=fallback,
            total_input_bytes=total_input,
            total_baseline_bytes=total_baseline,
            total_roi_bytes=total_roi,
            baseline_reduction_avg=sum(baseline_reductions) / len(baseline_reductions) if baseline_reductions else 0,
            roi_reduction_avg=sum(roi_reductions) / len(roi_reductions) if roi_reductions else 0,
            incremental_gain_avg=sum(incremental_gains) / len(incremental_gains) if incremental_gains else 0,
            positive_gain_ratio=positive_gains / len(incremental_gains) if incremental_gains else 0,
            avg_psnr=sum(psnr_values) / len(psnr_values) if psnr_values else None,
            min_psnr=min(psnr_values) if psnr_values else None,
            avg_roi_ratio=sum(roi_ratios) / len(roi_ratios) if roi_ratios else 0,
            avg_motion_ratio=sum(motion_ratios) / len(motion_ratios) if motion_ratios else 0,
            scenes_with_stationary_objects=stationary_count,
            tasks=[t.to_dict() for t in completed_tasks]
        )

        self._save_report()
        self._print_summary()

        return self.report

    def _save_report(self):
        """保存报告"""
        if not self.report:
            return

        report_path = self.reports_dir / f"{self.report.report_id}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.report.to_dict(), f, indent=2, ensure_ascii=False)

        print(f"\n[M1] Report saved to: {report_path}")

    def _print_summary(self):
        """打印摘要"""
        if not self.report:
            return

        r = self.report
        print("\n" + "=" * 70)
        print(f"M1 EXPERIMENT REPORT: {r.experiment_name}")
        print("=" * 70)
        print(f"Tasks:        {r.completed_tasks}/{r.total_tasks} completed, {r.failed_tasks} failed")
        print(f"Conservative: {r.conservative_tasks}, Fallback: {r.fallback_tasks}")
        print()
        print(f"Input:        {self._format_bytes(r.total_input_bytes)}")
        print(f"Baseline:     {self._format_bytes(r.total_baseline_bytes)} ({r.baseline_reduction_avg:+.1%})")
        print(f"ROI:          {self._format_bytes(r.total_roi_bytes)} ({r.roi_reduction_avg:+.1%})")
        print()
        print(f"Avg incremental gain: {r.incremental_gain_avg:+.2%}")
        print(f"Positive gain ratio:  {r.positive_gain_ratio:.0%}")
        print()
        print(f"ROI ratio avg:   {r.avg_roi_ratio:.1%}")
        print(f"Motion ratio avg: {r.avg_motion_ratio:.1%}")
        print(f"Stationary scenes: {r.scenes_with_stationary_objects}")

        if r.avg_psnr:
            print(f"Avg PSNR: {r.avg_psnr:.2f} dB")
        if r.min_psnr:
            print(f"Min PSNR: {r.min_psnr:.2f} dB")

        print("=" * 70)

    def _format_bytes(self, bytes_val: int) -> str:
        """格式化字节大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f} PB"


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='M1: ROI 保护 + 背景模糊批量处理')

    parser.add_argument('input_files', nargs='+', help='输入视频文件列表')
    parser.add_argument('--name', default='m1-roi-blur', help='实验名称')
    parser.add_argument('--output-dir', default='./m1_results', help='输出目录')
    parser.add_argument('--crf', type=int, default=28, help='CRF 质量因子 (默认: 28)')
    parser.add_argument('--preset', default='medium', help='编码预设 (默认: medium)')
    parser.add_argument('--motion-threshold', type=int, default=25, help='运动检测阈值')
    parser.add_argument('--blur-kernel', type=int, default=21, help='模糊核大小')
    parser.add_argument('--ffmpeg', default='ffmpeg', help='FFmpeg 路径')
    parser.add_argument('--ffprobe', default='ffprobe', help='FFprobe 路径')

    args = parser.parse_args()

    # 创建运行器
    runner = M1Runner(
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

        runner.add_task(
            input_file,
            crf=args.crf,
            preset=args.preset,
            motion_threshold=args.motion_threshold,
            blur_kernel=args.blur_kernel
        )

    if not runner.tasks:
        print("[ERROR] No valid input files")
        return 1

    # 运行
    report = runner.run()

    # 检查结果
    if report.failed_tasks == 0 and report.positive_gain_ratio > 0.5:
        print("\n[PASS] M1 experiment completed with positive incremental gains")
        return 0
    elif report.failed_tasks == 0:
        print("\n[WARN] Tasks completed but incremental gains are limited")
        return 0
    else:
        print(f"\n[FAIL] {report.failed_tasks} tasks failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
