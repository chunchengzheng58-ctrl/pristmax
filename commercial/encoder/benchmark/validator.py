"""
M0 Benchmark: Quality Validator

验证编码输出的质量，确保可播放性、时间覆盖和媒体完整性。
禁止假设输出有效，必须逐项验证。
"""
import os
import json
import subprocess
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple


@dataclass
class QualityMetrics:
    """质量指标"""
    # 完整性
    is_playable: bool = False
    duration_matches: bool = False
    has_video: bool = False
    has_audio: bool = False

    # 时间覆盖
    input_duration_sec: Optional[float] = None
    output_duration_sec: Optional[float] = None
    duration_diff_sec: Optional[float] = None
    duration_diff_percent: Optional[float] = None

    # 帧覆盖
    input_frame_count: Optional[int] = None
    output_frame_count: Optional[int] = None
    frame_diff: Optional[int] = None

    # 画质指标
    psnr_avg: Optional[float] = None
    psnr_min: Optional[float] = None
    ssim_avg: Optional[float] = None

    # 错误
    decode_error: Optional[str] = None
    validation_error: Optional[str] = None

    # 验证时间
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class QualityValidator:
    """
    质量验证器

    验证项目：
    1. 可播放性 - 视频能否正常解码
    2. 时间覆盖 - 时长是否匹配
    3. 帧覆盖 - 帧数是否匹配
    4. 画质指标 - PSNR/SSIM (如果提供参考)
    """

    def __init__(self, ffprobe_path: str = "ffprobe", ffmpeg_path: str = "ffmpeg"):
        self.ffprobe_path = ffprobe_path
        self.ffmpeg_path = ffmpeg_path

    def validate(
        self,
        input_path: str,
        output_path: str,
        calculate_metrics: bool = True
    ) -> QualityMetrics:
        """
        验证输出质量

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            calculate_metrics: 是否计算 PSNR/SSIM

        Returns:
            QualityMetrics: 质量指标
        """
        metrics = QualityValidator(timestamp=datetime.now().isoformat())

        # 1. 检查文件存在
        if not os.path.exists(output_path):
            metrics.validation_error = "Output file not found"
            return metrics

        # 2. 验证可播放性
        metrics.is_playable = self._check_playable(output_path)
        if not metrics.is_playable:
            metrics.decode_error = "Failed to decode output"
            return metrics

        # 3. 收集媒体信息
        input_info = self._probe_file(input_path)
        output_info = self._probe_file(output_path)

        if not input_info or not output_info:
            metrics.validation_error = "Failed to probe media files"
            return metrics

        # 4. 验证时间覆盖
        metrics.input_duration_sec = input_info.get('duration')
        metrics.output_duration_sec = output_info.get('duration')

        if metrics.input_duration_sec and metrics.output_duration_sec:
            metrics.duration_diff_sec = abs(
                metrics.input_duration_sec - metrics.output_duration_sec
            )
            # 允许 1% 的误差
            if metrics.input_duration_sec > 0:
                metrics.duration_diff_percent = (
                    metrics.duration_diff_sec / metrics.input_duration_sec * 100
                )
            metrics.duration_matches = metrics.duration_diff_percent <= 1.0

        # 5. 验证帧覆盖
        metrics.input_frame_count = input_info.get('frame_count')
        metrics.output_frame_count = output_info.get('frame_count')

        if metrics.input_frame_count and metrics.output_frame_count:
            metrics.frame_diff = abs(
                metrics.input_frame_count - metrics.output_frame_count
            )
            # 帧数差异应在 2% 以内
            if metrics.input_frame_count > 0:
                frame_diff_pct = metrics.frame_diff / metrics.input_frame_count * 100
                metrics.duration_matches = metrics.duration_matches and (frame_diff_pct <= 2.0)

        # 6. 检查音视频流
        metrics.has_video = output_info.get('has_video', False)
        metrics.has_audio = output_info.get('has_audio', False)

        # 7. 计算画质指标 (如果需要)
        if calculate_metrics and metrics.is_playable:
            quality = self._calculate_metrics(input_path, output_path)
            metrics.psnr_avg = quality.get('psnr_avg')
            metrics.psnr_min = quality.get('psnr_min')
            metrics.ssim_avg = quality.get('ssim_avg')

        return metrics

    def _check_playable(self, file_path: str) -> bool:
        """检查视频是否可播放"""
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'error',
                '-select_streams', 'v:0',
                '-count_frames',
                '-show_entries', 'stream=codec_type',
                '-of', 'json',
                file_path
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if proc.returncode != 0:
                return False

            data = json.loads(proc.stdout)
            streams = data.get('streams', [])
            return len(streams) > 0

        except Exception:
            return False

    def _probe_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """探测文件媒体信息"""
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                '-count_frames',
                file_path
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if proc.returncode != 0:
                return None

            data = json.loads(proc.stdout)

            result = {}

            # 解析格式
            if 'format' in data:
                fmt = data['format']
                result['duration'] = float(fmt.get('duration', 0))

            # 解析流
            has_video = False
            has_audio = False
            frame_count = 0

            for stream in data.get('streams', []):
                stype = stream.get('codec_type')

                if stype == 'video':
                    has_video = True
                    if stream.get('nb_frames'):
                        frame_count = max(frame_count, int(stream['nb_frames']))

                elif stype == 'audio':
                    has_audio = True

            result['has_video'] = has_video
            result['has_audio'] = has_audio
            result['frame_count'] = frame_count if frame_count > 0 else None

            return result

        except Exception:
            return None

    def _calculate_metrics(
        self,
        input_path: str,
        output_path: str
    ) -> Dict[str, float]:
        """
        计算画质指标 (PSNR, SSIM)

        使用 FFmpeg + libvmaf 或内置指标
        """
        result = {}

        # 简单检查：比较帧数和时间
        # 完整实现需要使用 VMAF 或原生 FFmpeg 过滤器

        try:
            # 尝试使用 psnr 过滤器
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-i', output_path,
                '-lavfi', 'psnr',
                '-f', 'null',
                '-'
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            # 解析输出中的 PSNR 值
            output = proc.stderr + proc.stdout
            for line in output.split('\n'):
                if 'psnr' in line.lower() and 'average' in line.lower():
                    # 格式: [Parsed_psnr_0 @ ...] PSNR y:XX.XX u:XX.XX v:XX.XX average:XX.XX ...
                    parts = line.split('average:')
                    if len(parts) > 1:
                        try:
                            result['psnr_avg'] = float(parts[1].split()[0])
                        except:
                            pass

        except Exception:
            pass

        return result

    def validate_batch(
        self,
        pairs: List[Tuple[str, str]],
        calculate_metrics: bool = True
    ) -> List[QualityMetrics]:
        """
        批量验证

        Args:
            pairs: [(input, output), ...] 文件对列表
            calculate_metrics: 是否计算画质

        Returns:
            List[QualityMetrics]: 质量指标列表
        """
        results = []
        for input_path, output_path in pairs:
            metrics = self.validate(input_path, output_path, calculate_metrics)
            results.append(metrics)
        return results


@dataclass
class ValidationReport:
    """验证报告"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    playability_failures: int = 0
    duration_failures: int = 0
    frame_failures: int = 0
    quality_failures: int = 0

    metrics: List[QualityMetrics] = None

    timestamp: str = ""

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = []

    def to_dict(self) -> dict:
        return {
            'total': self.total,
            'passed': self.passed,
            'failed': self.failed,
            'playability_failures': self.playability_failures,
            'duration_failures': self.duration_failures,
            'frame_failures': self.frame_failures,
            'quality_failures': self.quality_failures,
            'pass_rate': self.passed / self.total if self.total > 0 else 0,
            'metrics': [m.to_dict() for m in self.metrics],
            'timestamp': self.timestamp
        }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='验证视频输出质量')
    parser.add_argument('input', help='输入 (参考) 文件')
    parser.add_argument('output', help='输出 (待验证) 文件')
    parser.add_argument('--output-json', help='输出报告 JSON')

    args = parser.parse_args()

    validator = QualityValidator()
    metrics = validator.validate(args.input, args.output)

    print(json.dumps(metrics.to_dict(), indent=2))

    if args.output_json:
        with open(args.output_json, 'w', encoding='utf-8') as f:
            json.dump(metrics.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"报告已保存到: {args.output_json}")


if __name__ == '__main__':
    main()
