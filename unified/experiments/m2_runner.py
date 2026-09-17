"""
M2 Runner: ASVC and BLUE Comparative Experiment

M2 主程序: 批量执行 ASVC 和 BLUE 实验，生成对比报告。

M2 验收标准:
- ASVC: 验证裁剪比例、背景刷新、独立解码
- BLUE: 检查背景老化、静止目标、局部最差窗口
- 完整计入参考数据与索引
- 若收益不足以覆盖成本，停止产品化该路线
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

from .asvc import ASVCProcessor, BackgroundEstimator
from .blue import BackgroundFreezer, MotionCompensator
from .benchmark import H265Encoder, QualityValidator


@dataclass
class ExperimentResult:
    """单个实验结果"""
    experiment_id: str
    experiment_type: str  # "asvc" or "blue"
    input_path: str
    status: str = "pending"

    # 输入信息
    input_size_bytes: int = 0
    input_frames: int = 0

    # 处理结果
    output_size_bytes: int = 0
    processed_frames: int = 0

    # 质量
    avg_psnr: Optional[float] = None
    min_psnr: Optional[float] = None

    # 方法特定结果
    method_specific: Dict[str, Any] = None

    # 成本分析
    reference_overhead_bytes: int = 0  # 参考数据开销
    total_cost_bytes: int = 0  # 总成本 (输出 + 开销)

    # 收益
    reduction_ratio: float = 0.0  # 相对原文件降量率
    net_benefit_ratio: float = 0.0  # 净收益 (扣除开销后)

    # 错误
    error: Optional[str] = None

    def __post_init__(self):
        if self.method_specific is None:
            self.method_specific = {}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class M2Report:
    """M2 实验报告"""
    report_id: str
    experiment_name: str
    created_at: str

    # 实验统计
    total_experiments: int = 0
    completed_experiments: int = 0
    failed_experiments: int = 0

    # ASVC 结果汇总
    asvc_experiments: List[Dict] = field(default_factory=list)
    asvc_avg_reduction: float = 0.0
    asvc_avg_clipping: float = 0.0

    # BLUE 结果汇总
    blue_experiments: List[Dict] = field(default_factory=list)
    blue_experiments_avg_reduction: float = 0.0
    blue_local_failures: int = 0

    # 对比分析
    baseline_reduction: float = 0.0  # 普通 H.265 基线
    best_method: str = ""  # asvc / blue / baseline
    best_reduction: float = 0.0

    # 推荐
    recommendation: str = ""  # 继续/停止/修改

    def to_dict(self) -> dict:
        return asdict(self)


class M2Runner:
    """
    M2 实验运行器

    执行流程:
    1. 运行 ASVC 实验
    2. 运行 BLUE 实验
    3. 运行基线 (H.265)
    4. 生成对比报告
    5. 给出推荐
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
        self.asvc_dir = self.output_dir / "asvc"
        self.blue_dir = self.output_dir / "blue"
        self.baseline_dir = self.output_dir / "baseline"
        self.reports_dir = self.output_dir / "reports"

        for d in [self.asvc_dir, self.blue_dir, self.baseline_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

        # 组件
        self.h265_encoder = H265Encoder(ffmpeg_path=ffmpeg_path)
        self.quality_validator = QualityValidator(
            ffprobe_path=ffprobe_path,
            ffmpeg_path=ffmpeg_path
        )

        # 实验结果
        self.results: List[ExperimentResult] = []

    def run_asvc(self, input_path: str) -> ExperimentResult:
        """运行 ASVC 实验"""
        result = ExperimentResult(
            experiment_id=f"asvc-{len(self.results)}",
            experiment_type="asvc",
            input_path=input_path
        )

        try:
            print(f"[M2] Running ASVC: {input_path}")

            # ASVC 处理
            processor = ASVCProcessor(gop_size=12)
            asvc_result = processor.process(input_path, str(self.asvc_dir))

            if asvc_result.error:
                result.error = asvc_result.error
                result.status = "failed"
                return result

            result.status = "completed"
            result.input_frames = asvc_result.total_frames
            result.output_size_bytes = asvc_result.total_output_bytes
            result.processed_frames = asvc_result.total_frames

            # 计算平均裁剪比例
            avg_clipping = sum(
                gop.clipping_ratio for gop in asvc_result.gops if gop.has_background
            ) / len([g for g in asvc_result.gops if g.has_background]) if asvc_result.gops else 0

            result.method_specific = {
                'gop_count': asvc_result.gop_count,
                'avg_clipping_ratio': avg_clipping,
                'gops_with_background': sum(1 for g in asvc_result.gops if g.has_background)
            }

            # 成本分析
            result.reference_overhead_bytes = asvc_result.index_size_bytes

            # 计算收益
            input_size = os.path.getsize(input_path)
            result.input_size_bytes = input_size
            result.total_cost_bytes = result.output_size_bytes + result.reference_overhead_bytes

            if input_size > 0:
                result.reduction_ratio = 1 - (result.output_size_bytes / input_size)
                result.net_benefit_ratio = 1 - (result.total_cost_bytes / input_size)

            print(f"[M2] ASVC completed: reduction={result.reduction_ratio:.2%}, clipping={avg_clipping:.2%}")

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            print(f"[M2] ASVC failed: {e}")

        return result

    def run_blue(self, input_path: str) -> ExperimentResult:
        """运行 BLUE 实验"""
        result = ExperimentResult(
            experiment_id=f"blue-{len(self.results)}",
            experiment_type="blue",
            input_path=input_path
        )

        try:
            print(f"[M2] Running BLUE: {input_path}")

            output_path = str(self.blue_dir / f"{Path(input_path).stem}_blue.mp4")

            # BLUE 处理
            freezer = BackgroundFreezer(
                seed_interval=30,
                quality_threshold=30.0
            )
            blue_result = freezer.process(input_path, output_path)

            if blue_result.error:
                result.error = blue_result.error
                result.status = "failed"
                return result

            result.status = "completed"
            result.input_frames = blue_result.total_frames
            result.processed_frames = blue_result.processed_frames
            result.output_size_bytes = blue_result.output_size_bytes

            result.method_specific = {
                'frozen_frames': blue_result.frozen_frames,
                'bypass_frames': blue_result.bypass_frames,
                'frozen_ratio': blue_result.frozen_frames / blue_result.processed_frames if blue_result.processed_frames > 0 else 0,
                'local_failures': blue_result.local_failures
            }

            # 成本分析 (BLUE 主要是 seed 帧的开销)
            result.reference_overhead_bytes = 0  # 简化

            # 计算收益
            input_size = os.path.getsize(input_path)
            result.input_size_bytes = input_size
            result.total_cost_bytes = result.output_size_bytes

            if input_size > 0:
                result.reduction_ratio = 1 - (result.output_size_bytes / input_size)
                result.net_benefit_ratio = result.reduction_ratio

            print(f"[M2] BLUE completed: reduction={result.reduction_ratio:.2%}, failures={blue_result.local_failures}")

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            print(f"[M2] BLUE failed: {e}")

        return result

    def run_baseline(self, input_path: str) -> ExperimentResult:
        """运行 H.265 基线实验"""
        result = ExperimentResult(
            experiment_id=f"baseline-{len(self.results)}",
            experiment_type="baseline",
            input_path=input_path
        )

        try:
            print(f"[M2] Running baseline: {input_path}")

            output_path = str(self.baseline_dir / f"{Path(input_path).stem}_baseline.mp4")

            # H.265 编码
            encode_result = self.h265_encoder.encode(
                input_path,
                output_path,
                preset="medium",
                crf=28
            )

            if encode_result.error:
                result.error = encode_result.error
                result.status = "failed"
                return result

            result.status = "completed"
            result.output_size_bytes = encode_result.output_size_bytes

            # 质量验证
            quality = self.quality_validator.validate(input_path, output_path)
            result.avg_psnr = quality.psnr_avg
            result.min_psnr = quality.psnr_min

            # 计算收益
            input_size = os.path.getsize(input_path)
            result.input_size_bytes = input_size
            result.total_cost_bytes = result.output_size_bytes

            if input_size > 0:
                result.reduction_ratio = 1 - (result.output_size_bytes / input_size)

            print(f"[M2] Baseline completed: reduction={result.reduction_ratio:.2%}")

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            print(f"[M2] Baseline failed: {e}")

        return result

    def run_experiment(self, input_path: str) -> List[ExperimentResult]:
        """
        运行完整实验 (ASVC + BLUE + Baseline)

        Args:
            input_path: 输入视频路径

        Returns:
            List[ExperimentResult]: 实验结果列表
        """
        results = []

        # 运行三种方法
        results.append(self.run_asvc(input_path))
        results.append(self.run_blue(input_path))
        results.append(self.run_baseline(input_path))

        self.results.extend(results)
        return results

    def generate_report(self) -> M2Report:
        """生成实验报告"""
        completed = [r for r in self.results if r.status == "completed"]

        # 分类结果
        asvc_results = [r for r in completed if r.experiment_type == "asvc"]
        blue_results = [r for r in completed if r.experiment_type == "blue"]
        baseline_results = [r for r in completed if r.experiment_type == "baseline"]

        # 计算平均值
        asvc_avg_reduction = sum(r.reduction_ratio for r in asvc_results) / len(asvc_results) if asvc_results else 0
        asvc_avg_clipping = sum(r.method_specific.get('avg_clipping_ratio', 0) for r in asvc_results) / len(asvc_results) if asvc_results else 0

        blue_avg_reduction = sum(r.reduction_ratio for r in blue_results) / len(blue_results) if blue_results else 0
        blue_local_failures = sum(r.method_specific.get('local_failures', 0) for r in blue_results)

        baseline_avg_reduction = sum(r.reduction_ratio for r in baseline_results) / len(baseline_results) if baseline_results else 0

        # 确定最佳方法
        all_reductions = [
            ("asvc", asvc_avg_reduction),
            ("blue", blue_avg_reduction),
            ("baseline", baseline_avg_reduction)
        ]
        best = max(all_reductions, key=lambda x: x[1])

        # 生成推荐
        recommendation = "stop"
        if best[1] > baseline_avg_reduction * 1.1:  # 比基线好 10% 以上
            if asvc_avg_clipping < 0.05:  # 裁剪比例低
                recommendation = "continue_asvc"
            else:
                recommendation = "continue_blue"
        elif best[1] > baseline_avg_reduction:
            recommendation = "continue_with_tuning"

        report = M2Report(
            report_id=f"m2-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            experiment_name=self.experiment_name,
            created_at=datetime.now().isoformat(),
            total_experiments=len(self.results),
            completed_experiments=len(completed),
            failed_experiments=len(self.results) - len(completed),
            asvc_experiments=[r.to_dict() for r in asvc_results],
            asvc_avg_reduction=asvc_avg_reduction,
            asvc_avg_clipping=asvc_avg_clipping,
            blue_experiments=[r.to_dict() for r in blue_results],
            blue_experiments_avg_reduction=blue_avg_reduction,
            blue_local_failures=blue_local_failures,
            baseline_reduction=baseline_avg_reduction,
            best_method=best[0],
            best_reduction=best[1],
            recommendation=recommendation
        )

        self._save_report(report)
        self._print_summary(report)

        return report

    def _save_report(self, report: M2Report):
        """保存报告"""
        report_path = self.reports_dir / f"{report.report_id}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"\n[M2] Report saved to: {report_path}")

    def _print_summary(self, report: M2Report):
        """打印摘要"""
        print("\n" + "=" * 70)
        print(f"M2 EXPERIMENT REPORT: {report.experiment_name}")
        print("=" * 70)
        print(f"Experiments: {report.completed_experiments}/{report.total_experiments} completed")
        print()
        print(f"ASVC:  avg reduction={report.asvc_avg_reduction:.2%}, avg clipping={report.asvc_avg_clipping:.2%}")
        print(f"BLUE:  avg reduction={report.blue_experiments_avg_reduction:.2%}, failures={report.blue_local_failures}")
        print(f"BASE:  avg reduction={report.baseline_reduction:.2%}")
        print()
        print(f"Best method: {report.best_method} ({report.best_reduction:.2%})")
        print(f"Recommendation: {report.recommendation}")
        print("=" * 70)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='M2: ASVC 与 BLUE 对比实验')

    parser.add_argument('input_files', nargs='+', help='输入视频文件列表')
    parser.add_argument('--name', default='m2-comparison', help='实验名称')
    parser.add_argument('--output-dir', default='./m2_results', help='输出目录')

    args = parser.parse_args()

    runner = M2Runner(
        experiment_name=args.name,
        output_dir=args.output_dir
    )

    # 运行实验
    for input_file in args.input_files:
        if not os.path.exists(input_file):
            print(f"[WARN] File not found: {input_file}, skipping...")
            continue

        print(f"\n[M2] Processing: {input_file}")
        runner.run_experiment(input_file)

    # 生成报告
    report = runner.generate_report()

    return 0


if __name__ == '__main__':
    sys.exit(main())
