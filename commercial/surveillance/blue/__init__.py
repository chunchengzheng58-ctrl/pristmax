"""
M2 BLUE Module: Background Freezing with Quality Monitoring

BLUE (Background Learning with Unified Embedding) 处理模块

核心功能:
- 持久 seed 背景生成
- 运动补偿
- 质量监控
- 质量不足时旁路
"""

from .blue.freeze import (
    BackgroundFreezer,
    MotionCompensator,
    BLUEResult,
    QualityWindow
)

__all__ = [
    'BackgroundFreezer',
    'MotionCompensator',
    'BLUEResult',
    'QualityWindow',
]
