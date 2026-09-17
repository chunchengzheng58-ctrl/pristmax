"""
M1 Background Blur: Background Blurring for Video Compression

背景模糊处理: 对非 ROI 区域进行模糊处理，降低编码复杂度。
这是 M1 的核心模块。

关键论文参考:
- 03 Background Blurring: ROI 保留 + 背景低通 + 标准编码器
- 流程: 对象检测/人工选定 ROI → 模糊整帧 → 用原始 ROI 覆盖回去 → 标准编码器

限制:
- 背景模糊不可逆，需要另存原件
- 需要保护 ROI 区域不被模糊影响
- 背景纹理被丢弃，不支持完美还原
"""
import cv2
import numpy as np
from dataclasses import dataclass, asdict
from typing import Optional, Tuple
from pathlib import Path


@dataclass
class BlurResult:
    """模糊处理结果"""
    # 处理统计
    input_path: str = ""
    output_path: str = ""
    frame_count: int = 0
    processed_frames: int = 0

    # 模糊参数
    blur_kernel_size: int = 21  # 高斯模糊核大小
    blur_sigma: float = 0  # 自动计算
    roi_mask_ratio: float = 0.0  # ROI 占比

    # 质量指标
    input_avg_brightness: float = 0.0
    output_avg_brightness: float = 0.0
    brightness_diff: float = 0.0

    # 压缩效果预估
    estimated_compression_gain: float = 0.0  # 预估压缩增益

    # 错误
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class BackgroundBlurrer:
    """
    背景模糊处理器

    处理流程:
    1. 对每一帧应用高斯模糊 (模糊非 ROI 区域)
    2. 将 ROI 区域保持清晰
    3. 边缘羽化避免硬边界
    """

    def __init__(
        self,
        blur_kernel: int = 21,       # 模糊核大小 (必须是奇数)
        feather_pixels: int = 5,     # 边缘羽化像素
        blur_sigma: float = 0,       # 0 = 自动计算
    ):
        if blur_kernel % 2 == 0:
            blur_kernel += 1  # 确保是奇数

        self.blur_kernel = blur_kernel
        self.feather_pixels = feather_pixels
        self.blur_sigma = blur_sigma

    def process_video(
        self,
        video_path: str,
        output_path: str,
        roi_mask: Optional[np.ndarray] = None,
        use_motion_mask: bool = True
    ) -> BlurResult:
        """
        处理视频，应用背景模糊

        Args:
            video_path: 输入视频
            output_path: 输出视频
            roi_mask: 可选的 ROI 掩码 (与帧同尺寸的二值图)
            use_motion_mask: 是否自动检测运动区域作为 ROI

        Returns:
            BlurResult: 处理结果
        """
        result = BlurResult()
        result.input_path = video_path

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            result.error = f"Cannot open video: {video_path}"
            return result

        # 获取视频参数
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        result.frame_count = frame_count

        # 创建输出视频
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        # 预计算模糊核
        blur_kernel = (self.blur_kernel, self.blur_kernel)
        if self.blur_sigma == 0:
            sigma = self.blur_kernel / 6  # 经验值
        else:
            sigma = self.blur_sigma

        prev_frame = None
        motion_mask = None
        total_brightness_input = 0
        total_brightness_output = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            result.processed_frames += 1

            # 计算当前帧平均亮度
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            total_brightness_input += np.mean(gray)

            # 获取/生成 ROI 掩码
            if roi_mask is not None:
                mask = roi_mask.copy()
            elif use_motion_mask:
                mask = self._compute_motion_mask(frame, prev_frame)
            else:
                # 全帧模糊，无 ROI
                mask = np.ones((height, width), dtype=np.uint8) * 255

            # 创建混合掩码 (带羽化)
            blended_mask = self._feather_mask(mask, width, height)

            # 应用模糊
            blurred_frame = cv2.GaussianBlur(frame, blur_kernel, sigma)

            # 创建掩码数组
            mask_3ch = cv2.merge([blended_mask, blended_mask, blended_mask])
            inv_mask_3ch = 255 - mask_3ch

            # 混合: ROI 保持清晰，非 ROI 模糊
            # result = frame * mask + blurred * (1 - mask)
            result_frame = cv2.add(
                cv2.multiply(frame.astype(np.float32), mask_3ch.astype(np.float32) / 255.0),
                cv2.multiply(blurred_frame.astype(np.float32), inv_mask_3ch.astype(np.float32) / 255.0)
            )
            result_frame = result_frame.astype(np.uint8)

            out.write(result_frame)

            # 计算输出帧平均亮度
            result_gray = cv2.cvtColor(result_frame, cv2.COLOR_BGR2GRAY)
            total_brightness_output += np.mean(result_gray)

            prev_frame = frame.copy()

        cap.release()
        out.release()

        result.output_path = output_path

        # 计算平均亮度
        if result.processed_frames > 0:
            result.input_avg_brightness = total_brightness_input / result.processed_frames
            result.output_avg_brightness = total_brightness_output / result.processed_frames
            result.brightness_diff = abs(result.input_avg_brightness - result.output_avg_brightness)

        # 估算压缩增益 (基于 ROI 占比)
        # 背景模糊后编码复杂度降低，文件大小减少约等于 ROI 占比的损失
        # 这只是粗略估算，实际效果需要编码后测量
        if mask is not None:
            roi_pixels = cv2.countNonZero(mask)
            total_pixels = width * height
            result.roi_mask_ratio = roi_pixels / total_pixels if total_pixels > 0 else 0

            # 背景占比越高，潜在压缩增益越大
            # 但实际增益取决于编码器
            bg_ratio = 1 - result.roi_mask_ratio
            result.estimated_compression_gain = bg_ratio * 0.3  # 预估最高 30% 增益

        return result

    def _compute_motion_mask(
        self,
        current_frame: np.ndarray,
        prev_frame: Optional[np.ndarray]
    ) -> np.ndarray:
        """
        计算运动区域掩码

        简单帧差法: 与前一帧差异超过阈值的区域视为运动区域
        """
        height, width = current_frame.shape[:2]

        if prev_frame is None:
            # 第一帧，无运动
            return np.zeros((height, width), dtype=np.uint8)

        # 转换为灰度
        curr_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

        # 帧差
        diff = cv2.absdiff(curr_gray, prev_gray)

        # 阈值
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

        # 形态学处理
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.dilate(thresh, kernel, iterations=2)

        # 膨胀连接临近区域
        thresh = cv2.erode(thresh, kernel, iterations=1)

        return thresh

    def _feather_mask(
        self,
        mask: np.ndarray,
        width: int,
        height: int
    ) -> np.ndarray:
        """
        对掩码边缘进行羽化，避免硬边界

        使用距离变换和平滑来创建渐变边缘
        """
        # 确保是 uint8
        if mask.dtype != np.uint8:
            mask = mask.astype(np.uint8)

        # 膨胀先扩大 ROI 区域
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(mask, kernel, iterations=self.feather_pixels)

        # 高斯平滑创建渐变
        feathered = cv2.GaussianBlur(dilated, (self.feather_pixels * 2 + 1, self.feather_pixels * 2 + 1), 0)

        return feathered

    def create_static_mask(
        self,
        width: int,
        height: int,
        roi_regions: list
    ) -> np.ndarray:
        """
        创建静态 ROI 掩码

        Args:
            width, height: 帧尺寸
            roi_regions: ROI 区域列表 [(x1, y1, x2, y2), ...]

        Returns:
            np.ndarray: 二值掩码
        """
        mask = np.zeros((height, width), dtype=np.uint8)

        for x1, y1, x2, y2 in roi_regions:
            # 确保坐标在范围内
            x1, x2 = max(0, x1), min(width, x2)
            y1, y2 = max(0, y1), min(height, y2)
            mask[y1:y2, x1:x2] = 255

        return mask


def main():
    """命令行入口"""
    import argparse
    import json

    parser = argparse.ArgumentParser(description='M1: 背景模糊处理')
    parser.add_argument('input', help='输入视频文件')
    parser.add_argument('output', help='输出视频文件')
    parser.add_argument('--blur-kernel', '-b', type=int, default=21, help='模糊核大小 (奇数, 默认: 21)')
    parser.add_argument('--feather', '-f', type=int, default=5, help='边缘羽化像素 (默认: 5)')
    parser.add_argument('--no-motion-mask', action='store_true', help='不使用运动掩码 (全帧模糊)')

    args = parser.parse_args()

    blurrer = BackgroundBlurrer(
        blur_kernel=args.blur_kernel,
        feather_pixels=args.feather
    )

    print(f"[Blur] Processing: {args.input}")
    print(f"[Blur] Output: {args.output}")

    result = blurrer.process_video(
        args.input,
        args.output,
        use_motion_mask=not args.no_motion_mask
    )

    print(f"[Blur] Results:")
    print(f"  - Processed frames: {result.processed_frames}/{result.frame_count}")
    print(f"  - ROI mask ratio: {result.roi_mask_ratio * 100:.1f}%")
    print(f"  - Estimated compression gain: {result.estimated_compression_gain * 100:.1f}%")
    print(f"  - Brightness diff: {result.brightness_diff:.2f}")

    if result.error:
        print(f"[ERROR] {result.error}")
    else:
        print(f"[OK] Processing complete")


if __name__ == '__main__':
    main()
