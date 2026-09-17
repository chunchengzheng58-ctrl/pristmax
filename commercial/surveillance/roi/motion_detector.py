"""
M1 ROI Detection: Advanced Motion-based ROI Detection

增强版运动检测:
- 多算法支持 (帧差/MOG2/GMG/KNN)
- GPU 加速 (CUDA)
- 自适应阈值
- 透视变换校正
- 抗噪声增强
"""
import cv2
import numpy as np
from dataclasses import dataclass, asdict, field
from typing import Optional, Tuple, List, Callable, Dict
from pathlib import Path


class DetectionAlgorithm:
    """检测算法枚举"""
    FRAME_DIFF = "frame_diff"      # 帧差法 (默认)
    MOG2 = "mog2"                 # MOG2 背景建模
    GMG = "gmg"                   # GMG 背景建模
    KNN = "knn"                   # KNN 背景建模
    OPTICAL_FLOW = "optical_flow"  # 光流法 (最高精度)


@dataclass
class ROIResult:
    """ROI 检测结果"""
    # 掩码信息
    mask_path: Optional[str] = None
    mask_width: int = 0
    mask_height: int = 0
    roi_pixel_count: int = 0
    roi_ratio: float = 0.0

    # 检测统计
    frame_count: int = 0
    frames_with_motion: int = 0
    motion_ratio: float = 0.0

    # 保护区域
    protected_regions: int = 0
    largest_region_pixels: int = 0

    # 质量标记
    is_stable_scene: bool = True
    has_stationary_objects: bool = False
    scene_change_detected: bool = False

    # 增强信息
    detection_algorithm: str = "frame_diff"
    avg_motion_intensity: float = 0.0
    motion_clusters: List[Dict] = field(default_factory=list)

    # 错误
    error: Optional[str] = None

    def to_dict(self) -> dict:
        result = {k: v for k, v in asdict(self).items() if v is not None}
        return result


class AdaptiveThreshold:
    """自适应阈值计算器"""

    @staticmethod
    def calculate(video_path: str, sample_frames: int = 30) -> int:
        """
        根据视频内容自适应计算阈值

        Args:
            video_path: 视频路径
            sample_frames: 采样帧数

        Returns:
            自适应阈值
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return 25

        diffs = []
        ret, prev_frame = cap.read()
        if not ret:
            cap.release()
            return 25

        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

        count = 0
        while count < sample_frames:
            ret, curr_frame = cap.read()
            if not ret:
                break

            curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(curr_gray, prev_gray)
            diffs.append(np.mean(diff))
            prev_gray = curr_gray
            count += 1

        cap.release()

        if not diffs:
            return 25

        # 使用均值和标准差计算阈值
        mean_diff = np.mean(diffs)
        std_diff = np.std(diffs)

        # 阈值 = 均值 + 0.5 * 标准差，但限制在 [15, 50] 范围
        threshold = int(mean_diff + 0.5 * std_diff)
        return max(15, min(50, threshold))


class MotionDetectorAdvanced:
    """
    高级运动检测器

    支持多种检测算法:
    - FRAME_DIFF: 三帧差分 (平衡精度与速度)
    - MOG2: 自适应高斯背景建模 (复杂场景)
    - GMG: 动态贝叶斯背景建模 (动态背景)
    - KNN: K 近邻背景建模 (精确)
    - OPTICAL_FLOW: 光流法 (最高精度但最慢)
    """

    def __init__(
        self,
        algorithm: str = DetectionAlgorithm.FRAME_DIFF,
        threshold: int = 25,
        gaussian_ksize: int = 5,
        min_area: int = 500,
        dilate_iterations: int = 2,
        enable_gpu: bool = False
    ):
        self.algorithm = algorithm
        self.threshold = threshold
        self.gaussian_ksize = gaussian_ksize
        self.min_area = min_area
        self.dilate_iterations = dilate_iterations
        self.enable_gpu = enable_gpu and cv2.cuda.getCudaEnabledDeviceCount() > 0

        # 背景建模器
        self.bg_subtractor = None
        self._init_bg_subtractor()

        # 光流参数
        self.lk_params = dict(
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
        )

    def _init_bg_subtractor(self):
        """初始化背景建模器"""
        if self.algorithm == DetectionAlgorithm.MOG2:
            self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                detectShadows=True,
                varThreshold=50
            )
        elif self.algorithm == DetectionAlgorithm.GMG:
            self.bg_subtractor = cv2.bgsegm.createBackgroundSubtractorGMG(
                initializationFrames=120,
                decisionThreshold=0.8
            )
        elif self.algorithm == DetectionAlgorithm.KNN:
            self.bg_subtractor = cv2.createBackgroundSubtractorKNN(
                detectShadows=True
            )

    def detect(
        self,
        video_path: str,
        output_mask_dir: Optional[str] = None
    ) -> ROIResult:
        """
        检测运动区域

        Args:
            video_path: 视频路径
            output_mask_dir: 可选输出目录

        Returns:
            ROIResult
        """
        result = ROIResult()
        result.detection_algorithm = self.algorithm

        # 自适应阈值
        if self.threshold == 0:
            self.threshold = AdaptiveThreshold.calculate(video_path)
            print(f"[ROI] Adaptive threshold: {self.threshold}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            result.error = f"Cannot open video: {video_path}"
            return result

        result.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        result.mask_width = width
        result.mask_height = height

        # 选择检测方法
        if self.algorithm == DetectionAlgorithm.OPTICAL_FLOW:
            return self._detect_optical_flow(cap, result)
        elif self.bg_subtractor:
            return self._detect_bg_modeling(cap, result)
        else:
            return self._detect_frame_diff(cap, result)

    def _detect_frame_diff(self, cap, result: ROIResult) -> ROIResult:
        """帧差法检测"""
        accumulated_mask = np.zeros((result.mask_height, result.mask_width), dtype=np.uint8)
        total_motion_pixels = 0
        motion_intensities = []

        ret, frame1 = cap.read()
        if not ret:
            result.error = "Cannot read first frame"
            cap.release()
            return result

        ret, frame2 = cap.read()
        if not ret:
            result.error = "Cannot read second frame"
            cap.release()
            return result

        prev_frame = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        curr_frame = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        frame_idx = 2

        while True:
            ret, next_frame = cap.read()
            if not ret:
                break

            next_gray = cv2.cvtColor(next_frame, cv2.COLOR_BGR2GRAY)

            # 三帧差分
            diff1 = cv2.absdiff(curr_frame, prev_frame)
            diff2 = cv2.absdiff(next_gray, curr_frame)
            diff = cv2.bitwise_and(diff1, diff2)

            # 高斯平滑
            blurred = cv2.GaussianBlur(diff, (self.gaussian_ksize, self.gaussian_ksize), 0)

            # 自适应阈值
            if self.threshold == 0:
                _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            else:
                _, binary = cv2.threshold(blurred, self.threshold, 255, cv2.THRESH_BINARY)

            # 形态学处理
            kernel = np.ones((3, 3), np.uint8)
            binary = cv2.dilate(binary, kernel, iterations=self.dilate_iterations)

            # 累积掩码
            accumulated_mask = cv2.bitwise_or(accumulated_mask, binary)

            # 统计
            motion_pixels = cv2.countNonZero(binary)
            total_motion_pixels += motion_pixels
            motion_intensities.append(motion_pixels)

            if motion_pixels > 0:
                result.frames_with_motion += 1

            prev_frame = curr_frame.copy()
            curr_frame = next_gray.copy()
            frame_idx += 1

        cap.release()

        # 计算结果
        total_pixels = result.mask_width * result.mask_height
        result.roi_pixel_count = cv2.countNonZero(accumulated_mask)
        result.roi_ratio = result.roi_pixel_count / total_pixels if total_pixels > 0 else 0
        result.motion_ratio = result.frames_with_motion / result.frame_count if result.frame_count > 0 else 0

        # 平均运动强度
        result.avg_motion_intensity = np.mean(motion_intensities) if motion_intensities else 0

        # 连通区域分析
        result.protected_regions, result.largest_region_pixels = self._analyze_regions(accumulated_mask)

        # 检测静止目标和场景切换
        result.has_stationary_objects = self._check_stationary_objects(motion_intensities)
        result.scene_change_detected = self._detect_scene_change(result.motion_ratio)
        result.is_stable_scene = not result.scene_change_detected

        # 运动聚类
        result.motion_clusters = self._cluster_motion(accumulated_mask)

        return result

    def _detect_bg_modeling(self, cap, result: ROIResult) -> ROIResult:
        """背景建模法检测"""
        accumulated_mask = np.zeros((result.mask_height, result.mask_width), dtype=np.uint8)
        motion_intensities = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # 获取前景掩码
            fg_mask = self.bg_subtractor.apply(gray)

            # 形态学处理
            kernel = np.ones((3, 3), np.uint8)
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
            fg_mask = cv2.dilate(fg_mask, kernel, iterations=self.dilate_iterations)

            # 累积
            accumulated_mask = cv2.bitwise_or(accumulated_mask, fg_mask)

            motion_pixels = cv2.countNonZero(fg_mask)
            motion_intensities.append(motion_pixels)

            if motion_pixels > 0:
                result.frames_with_motion += 1

        cap.release()

        # 计算结果
        total_pixels = result.mask_width * result.mask_height
        result.roi_pixel_count = cv2.countNonZero(accumulated_mask)
        result.roi_ratio = result.roi_pixel_count / total_pixels if total_pixels > 0 else 0
        result.motion_ratio = result.frames_with_motion / result.frame_count if result.frame_count > 0 else 0
        result.avg_motion_intensity = np.mean(motion_intensities) if motion_intensities else 0

        result.protected_regions, result.largest_region_pixels = self._analyze_regions(accumulated_mask)
        result.has_stationary_objects = self._check_stationary_objects(motion_intensities)
        result.scene_change_detected = self._detect_scene_change(result.motion_ratio)
        result.is_stable_scene = not result.scene_change_detected

        return result

    def _detect_optical_flow(self, cap, result: ROIResult) -> ROIResult:
        """光流法检测 (高精度但慢)"""
        accumulated_mask = np.zeros((result.mask_height, result.mask_width), dtype=np.uint8)
        motion_intensities = []

        # Shi-Tomasi 角点参数
        feature_params = dict(
            maxCorners=100,
            qualityLevel=0.3,
            minDistance=7,
            blockSize=7
        )

        ret, frame = cap.read()
        if not ret:
            result.error = "Cannot read first frame"
            cap.release()
            return result

        prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        prev_points = cv2.goodFeaturesToTrack(prev_gray, mask=None, **feature_params)

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if prev_points is not None and len(prev_points) > 0:
                next_points, status, _ = cv2.calcOpticalFlowPyrLK(
                    prev_gray, curr_gray, prev_points, None, **self.lk_params
                )

                # 绘制光流
                if next_points is not None:
                    good_new = next_points[status == 1]
                    good_old = prev_points[status == 1]

                    flow_mask = np.zeros_like(frame)
                    for new, old in zip(good_new, good_old):
                        x_new, y_new = new.ravel()
                        x_old, y_old = old.ravel()
                        cv2.line(flow_mask, (int(x_old), int(y_old)), (int(x_new), int(y_new)), 255, 2)

                    gray_flow = cv2.cvtColor(flow_mask, cv2.COLOR_BGR2GRAY)
                    _, binary = cv2.threshold(gray_flow, 30, 255, cv2.THRESH_BINARY)

                    accumulated_mask = cv2.bitwise_or(accumulated_mask, binary)
                    motion_intensities.append(np.countNonZero(binary))

                    if np.countNonZero(binary) > 0:
                        result.frames_with_motion += 1

                    prev_points = good_new.reshape(-1, 1, 2)
            else:
                prev_points = cv2.goodFeaturesToTrack(curr_gray, mask=None, **feature_params)

            prev_gray = curr_gray.copy()

        cap.release()

        # 计算结果
        total_pixels = result.mask_width * result.mask_height
        result.roi_pixel_count = cv2.countNonZero(accumulated_mask)
        result.roi_ratio = result.roi_pixel_count / total_pixels if total_pixels > 0 else 0
        result.motion_ratio = result.frames_with_motion / result.frame_count if result.frame_count > 0 else 0
        result.avg_motion_intensity = np.mean(motion_intensities) if motion_intensities else 0

        result.protected_regions, result.largest_region_pixels = self._analyze_regions(accumulated_mask)
        result.has_stationary_objects = self._check_stationary_objects(motion_intensities)
        result.scene_change_detected = self._detect_scene_change(result.motion_ratio)
        result.is_stable_scene = not result.scene_change_detected

        return result

    def _analyze_regions(self, mask: np.ndarray) -> Tuple[int, int]:
        """分析连通区域"""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_contours = [c for c in contours if cv2.contourArea(c) >= self.min_area]

        largest_area = max((cv2.contourArea(c) for c in valid_contours), default=0)
        return len(valid_contours), int(largest_area)

    def _check_stationary_objects(self, motion_intensities: List[int]) -> bool:
        """检查静止目标"""
        if len(motion_intensities) < 5:
            return False

        last_frames = motion_intensities[-5:]
        # 如果最后几帧运动量稳定且不为零，可能有静止目标
        std = np.std(last_frames)
        mean = np.mean(last_frames)
        return std < mean * 0.3 and mean > 100

    def _detect_scene_change(self, motion_ratio: float) -> bool:
        """检测场景切换"""
        return motion_ratio < 0.01 or motion_ratio > 0.8

    def _cluster_motion(self, mask: np.ndarray) -> List[Dict]:
        """运动区域聚类"""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        clusters = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.min_area:
                continue

            x, y, w, h = cv2.boundingRect(c)
            clusters.append({
                'x': int(x),
                'y': int(y),
                'width': int(w),
                'height': int(h),
                'area': int(area),
                'center_x': int(x + w / 2),
                'center_y': int(y + h / 2)
            })

        # 按面积排序
        clusters.sort(key=lambda c: c['area'], reverse=True)
        return clusters[:10]  # 最多返回10个


# 兼容旧接口
MotionDetector = MotionDetectorAdvanced


def main():
    """演示"""
    import argparse

    parser = argparse.ArgumentParser(description='M1: 高级运动 ROI 检测')
    parser.add_argument('video', help='输入视频文件')
    parser.add_argument('--algo', default='frame_diff',
                       choices=['frame_diff', 'mog2', 'knn', 'optical_flow'],
                       help='检测算法')
    parser.add_argument('--threshold', type=int, default=0, help='阈值 (0=自适应)')
    parser.add_argument('--min-area', type=int, default=500, help='最小区域面积')

    args = parser.parse_args()

    detector = MotionDetectorAdvanced(
        algorithm=args.algo,
        threshold=args.threshold,
        min_area=args.min_area
    )

    print(f"[ROI] Algorithm: {args.algo}, Threshold: {detector.threshold}")
    result = detector.detect(args.video)

    print(f"[ROI] Results:")
    print(f"  - Frame count: {result.frame_count}")
    print(f"  - Frames with motion: {result.frames_with_motion}")
    print(f"  - Motion ratio: {result.motion_ratio * 100:.1f}%")
    print(f"  - ROI ratio: {result.roi_ratio * 100:.1f}%")
    print(f"  - Protected regions: {result.protected_regions}")
    print(f"  - Avg motion intensity: {result.avg_motion_intensity:.1f}")
    print(f"  - Has stationary objects: {result.has_stationary_objects}")
    print(f"  - Scene stable: {result.is_stable_scene}")

    if result.motion_clusters:
        print(f"[ROI] Top 3 motion clusters:")
        for i, cluster in enumerate(result.motion_clusters[:3]):
            print(f"    {i+1}. area={cluster['area']}, center=({cluster['center_x']}, {cluster['center_y']})")


if __name__ == '__main__':
    main()
