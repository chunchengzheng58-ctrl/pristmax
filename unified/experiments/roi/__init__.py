"""
Pristmax M1: ROI Protection + Background Blur Module

M1 阶段目标: 实现运动 ROI 检测 + 背景模糊 + H.265 编码的完整流程。

模块:
- motion_detector: 基于帧差的运动目标检测
- background_blur: 背景模糊处理器
- roi_encoder: ROI 编码器 (安全版)

验收标准:
- 相对同配置普通编码器存在额外收益
- 客户选定的关键任务质量通过
- 任一硬门槛失败则保留基线候选或原件

核心原则:
- 原始文件绝对不修改
- 所有操作需要用户授权
- 保持文件完整性
"""

from .roi.motion_detector import (
    MotionDetector,
    ROIResult
)
from .roi.background_blur import (
    BackgroundBlurrer,
    BlurResult
)
from .roi.roi_encoder import (
    ROIEncoderSafe,
    ROIEncoderConfig,
    ROIEncoderResult,
    AuthorizeManager
)

# Backward compatibility
ROIEncoder = ROIEncoderSafe

__all__ = [
    'MotionDetector',
    'ROIResult',
    'BackgroundBlurrer',
    'BlurResult',
    'ROIEncoder',
    'ROIEncoderSafe',
    'ROIEncoderConfig',
    'ROIEncoderResult',
    'AuthorizeManager',
]
