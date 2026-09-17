"""
Pristmax M0 Benchmark Module

M0: Offline Baseline Benchmark Tool

模块:
- file_info: 文件信息收集 (哈希、媒体信息)
- encoder: H.265 编码基线 (安全版)
- validator: 质量验证
- benchmark: 主程序

用法:
    python -m experiments.benchmark.benchmark input.mp4 --output-dir ./results
"""

from .file_info import FileInfoCollector, MediaInfo
from .encoder import (
    H265Encoder,
    H265EncoderSafe,
    EncodeResult,
    IntegrityChecker,
    AuthorizeManager,
    EncodeMode,
    IntegrityStatus
)
from .validator import QualityValidator, QualityMetrics
from .benchmark import BenchmarkRunner, BenchmarkTask, BenchmarkReport

__all__ = [
    'FileInfoCollector',
    'MediaInfo',
    'H265Encoder',
    'H265EncoderSafe',
    'EncodeResult',
    'IntegrityChecker',
    'AuthorizeManager',
    'EncodeMode',
    'IntegrityStatus',
    'QualityValidator',
    'QualityMetrics',
    'BenchmarkRunner',
    'BenchmarkTask',
    'BenchmarkReport',
]
