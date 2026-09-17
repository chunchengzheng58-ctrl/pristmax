"""
M0 Benchmark: File Info Collector

收集文件的哈希、媒体信息，建立可追溯的基准。
"""
import os
import json
import hashlib
import subprocess
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


@dataclass
class MediaInfo:
    """媒体文件元信息"""
    # 文件基础信息
    path: str
    size_bytes: int
    sha256_hash: str
    file_time: str  # ISO format

    # 媒体信息 (ffprobe)
    duration_sec: Optional[float] = None
    frame_count: Optional[int] = None
    frame_rate: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    bitrate_kbps: Optional[int] = None
    container: Optional[str] = None

    # 分析标记
    has_audio: bool = False
    has_video: bool = False

    # 质量标记
    is_interlaced: bool = False
    color_space: Optional[str] = None

    # 错误记录
    ffprobe_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class FileInfoCollector:
    """
    收集文件的完整信息，包括：
    - SHA-256 哈希
    - ffprobe 媒体信息
    - 时间戳
    """

    def __init__(self, ffprobe_path: str = "ffprobe"):
        self.ffprobe_path = ffprobe_path

    def collect(self, file_path: str) -> MediaInfo:
        """
        收集单个文件的完整信息

        Args:
            file_path: 文件路径

        Returns:
            MediaInfo: 文件信息对象
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # 基本信息
        stat = os.stat(file_path)
        file_time = datetime.fromtimestamp(stat.st_mtime).isoformat()

        # 计算 SHA-256
        sha256_hash = self._compute_hash(file_path)

        # 收集 ffprobe 信息
        media_info = self._probe_media(file_path)

        return MediaInfo(
            path=file_path,
            size_bytes=stat.st_size,
            sha256_hash=sha256_hash,
            file_time=file_time,
            **media_info
        )

    def _compute_hash(self, file_path: str, chunk_size: int = 8192) -> str:
        """计算文件 SHA-256 哈希"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    def _probe_media(self, file_path: str) -> Dict[str, Any]:
        """
        使用 ffprobe 获取媒体信息

        Returns:
            dict: 媒体信息字典
        """
        result = {
            'ffprobe_error': None,
            'has_video': False,
            'has_audio': False,
        }

        try:
            # ffprobe 命令获取 JSON 输出
            cmd = [
                self.ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if proc.returncode != 0:
                result['ffprobe_error'] = proc.stderr.strip()
                return result

            data = json.loads(proc.stdout)

            # 解析格式信息
            if 'format' in data:
                fmt = data['format']
                result['duration_sec'] = float(fmt.get('duration', 0))
                result['bitrate_kbps'] = int(fmt.get('bit_rate', 0)) // 1000 if fmt.get('bit_rate') else None
                result['container'] = fmt.get('format_name', '').split(',')[0]

            # 解析流信息
            if 'streams' in data:
                for stream in data['streams']:
                    stype = stream.get('codec_type', '')

                    if stype == 'video':
                        result['has_video'] = True
                        result['width'] = stream.get('width')
                        result['height'] = stream.get('height')
                        result['video_codec'] = stream.get('codec_name', '').upper()
                        result['frame_rate'] = self._parse_frame_rate(stream.get('r_frame_rate', ''))
                        result['frame_count'] = stream.get('nb_frames')
                        result['is_interlaced'] = stream.get('field_order', 'progressive') != 'progressive'
                        result['color_space'] = stream.get('pix_fmt', '')

                    elif stype == 'audio':
                        result['has_audio'] = True
                        if not result['audio_codec']:
                            result['audio_codec'] = stream.get('codec_name', '').upper()

        except subprocess.TimeoutExpired:
            result['ffprobe_error'] = 'ffprobe timeout'
        except json.JSONDecodeError as e:
            result['ffprobe_error'] = f'JSON parse error: {e}'
        except Exception as e:
            result['ffprobe_error'] = str(e)

        return result

    def _parse_frame_rate(self, fps_str: str) -> Optional[float]:
        """解析帧率字符串 (如 "30/1")"""
        if not fps_str or '/' not in fps_str:
            return None
        try:
            num, den = fps_str.split('/')
            return float(num) / float(den)
        except:
            return None

    def collect_batch(self, file_paths: List[str]) -> List[MediaInfo]:
        """
        批量收集文件信息

        Args:
            file_paths: 文件路径列表

        Returns:
            List[MediaInfo]: 文件信息列表
        """
        results = []
        for path in file_paths:
            try:
                info = self.collect(path)
                results.append(info)
            except Exception as e:
                # 记录错误但继续处理其他文件
                results.append(MediaInfo(
                    path=path,
                    size_bytes=0,
                    sha256_hash='',
                    file_time='',
                    ffprobe_error=str(e)
                ))
        return results


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='收集视频文件的基准信息')
    parser.add_argument('input', help='输入文件路径')
    parser.add_argument('--output', '-o', help='输出 JSON 文件路径')
    parser.add_argument('--ffprobe', default='ffprobe', help='ffprobe 路径')

    args = parser.parse_args()

    collector = FileInfoCollector(ffprobe_path=args.ffprobe)
    info = collector.collect(args.input)

    output = info.to_dict()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"结果已保存到: {args.output}")
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
