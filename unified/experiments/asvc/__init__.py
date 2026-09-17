"""
M2 ASVC Module: Background Estimation and Differential Encoding

ASVC (Adaptive Semantic Video Coding) 处理模块

核心功能:
- 多尺度背景估计
- 运动补偿预测
- 自适应 GOP 分组
- 差分编码
"""

from .asvc.background_estimator import (
    MultiScaleBackgroundEstimator,
    MotionCompensatedPredictor,
    AdaptiveGOP,
    DifferentialEncoder,
    ASVCProcessor,
    ASVCResult,
    GOPResult
)

__all__ = [
    'MultiScaleBackgroundEstimator',
    'MotionCompensatedPredictor',
    'AdaptiveGOP',
    'DifferentialEncoder',
    'ASVCProcessor',
    'ASVCResult',
    'GOPResult',
]
