# M1: ROI 保护 + 背景模糊

**状态**: 已实现

**验收标准**:
- [x] 相对同配置普通编码器存在额外收益
- [x] 客户选定的关键任务质量通过
- [x] 任一硬门槛失败则保留基线候选或原件
- [x] 普通重编码节省不得归功于 ROI 算法

---

## 模块结构

```
experiments/
├── roi/
│   ├── __init__.py
│   ├── motion_detector.py     # 运动 ROI 检测
│   ├── background_blur.py     # 背景模糊处理
│   └── roi_encoder.py         # ROI 编码器 (核心)
├── roi_runner.py              # M1 批量处理
└── README.md
```

---

## 核心流程

```
原始视频
    ↓
┌─────────────────────┐
│  1. 运动 ROI 检测     │  ← MotionDetector
│     - 三帧差分        │
│     - 高斯平滑        │
│     - 连通区域分析     │
└─────────────────────┘
    ↓
┌─────────────────────┐
│  2. 判断处理模式     │
│     - normal: 正常   │
│     - conservative:  │
│       缩小模糊核     │
│     - fallback:     │
│       回退基线       │
└─────────────────────┘
    ↓
┌─────────────────────┐
│  3. 背景模糊处理     │  ← BackgroundBlurrer
│     - 高斯模糊        │
│     - ROI 保持清晰   │
│     - 边缘羽化        │
└─────────────────────┘
    ↓
┌─────────────────────┐
│  4. H.265 编码      │  ← H265Encoder
│     - 同配置基线     │
│     - CRF=28       │
└─────────────────────┘
    ↓
┌─────────────────────┐
│  5. 质量验证        │  ← QualityValidator
│     - 可播放性       │
│     - 时长匹配       │
│     - PSNR/SSIM    │
└─────────────────────┘
    ↓
输出报告 + 对比分析
```

---

## 保守路径条件

满足以下任一条件时使用保守路径:
- 场景不稳定 (scene_change_detected)
- 运动比例 > 80% 或 < 1%
- 检测到静止目标 (停住的人车)

保守路径:
- 使用较小的模糊核 (blur_kernel / 2)
- 保留更多原始画面信息

---

## 使用方法

### 单个视频处理

```bash
python -m experiments.roi.roi_encoder input.mp4 ./output \
    --crf 28 --blur-kernel 21 --motion-threshold 25
```

### 批量处理

```bash
python experiments/roi_runner.py video1.mp4 video2.mp4 video3.mp4 \
    --name "m1-experiment-01" \
    --output-dir ./m1_results \
    --crf 28 \
    --blur-kernel 21
```

### 单独使用运动检测

```bash
python -m experiments.roi.motion_detector input.mp4 \
    --threshold 25 \
    --min-area 500 \
    --output mask.mp4
```

### 单独使用背景模糊

```bash
python -m experiments.roi.background_blur input.mp4 output.mp4 \
    --blur-kernel 21 --feather 5
```

---

## 输出指标

| 指标 | 说明 |
|------|------|
| `roi_ratio` | ROI 占画面比例 |
| `motion_ratio` | 有运动帧的比例 |
| `has_stationary_objects` | 是否有静止目标 |
| `processing_mode` | normal / conservative / fallback |
| `baseline_reduction_ratio` | 基线降量率 |
| `roi_reduction_ratio` | ROI 降量率 |
| `incremental_gain` | 相对基线的增量收益 |
| `psnr_avg` | 平均 PSNR (dB) |

---

## 论文参考

| 论文 | 贡献 | 实现 |
|------|------|------|
| 03 Background Blurring | 运动掩码 + 背景模糊 | ✅ MotionDetector + BackgroundBlurrer |
| 07 ROI Extraction | 帧差 + 阈值 + 连通区域 | ✅ MotionDetector |
| 04 BLUE | 静止目标保护 | ✅ 保守路径 |

---

## 下一步

**M2**: ASVC 与 BLUE 独立实验
- 独立验证背景重建
- 检查背景老化
- 验证随机读取

---

## 限制

- 静止目标可能漏检 (需要补充目标检测)
- 镜头运动场景使用保守路径
- 背景模糊不可逆，需另存原件
