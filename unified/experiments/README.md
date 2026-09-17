# Pristmax Experiments - 安全优化版

## 核心原则

| 原则 | 说明 |
|------|------|
| **不修改原始文件** | 所有操作只读取原始文件，创建新文件 |
| **用户授权** | 所有危险操作(删除/覆盖)需要用户明确授权 |
| **完整性校验** | SHA-256 哈希验证文件完整性 |
| **可追溯** | 审计日志记录所有操作 |
| **可恢复** | 删除前备份，支持恢复 |

---

## 安全模块

### H265Encoder (encoder.py)
```python
encoder = H265EncoderSafe()

# 请求授权
record_id = encoder.prepare_encode(input_path, output_path)
print(f"Authorization required. Record ID: {record_id}")

# 用户授权后执行
encoder.authorizer.authorize(record_id)
result = encoder.encode(input_path, output_path, record_id=record_id)
```

### ROIEncoder (roi_encoder.py)
```python
encoder = ROIEncoderSafe()

# 请求授权
record_id = encoder.request_encode(input_path, output_dir)
encoder.authorize(record_id)

# 执行 (只读原始文件，创建新文件)
result = encoder.encode(input_path, output_dir, record_id=record_id)
```

### DedupIndex (dedup/index.py)
```python
index = DedupIndexSafe()

# 添加块 (自动增加引用计数)
index.add_chunk(chunk_id, content_hash, size, storage_path)

# 请求删除 (ref_count 必须为 0)
request_id = index.request_delete(content_hash)

# 用户授权后删除 (删除前自动备份)
index.authorize_delete(request_id)

# 支持从备份恢复
index.restore_from_backup(content_hash)
```

---

## 安全功能

| 功能 | 实现 |
|------|------|
| 完整性校验 | SHA-256 哈希计算 |
| 用户授权 | AuthorizeManager 请求/授权流程 |
| 审计日志 | AuditLog 记录所有操作 |
| 删除保护 | ref_count > 0 阻止删除 |
| 删除备份 | 删除前自动备份到 backup_dir |
| 可逆性 | restore_from_backup 恢复数据 |

---

## 目录结构

```
experiments/
├── benchmark/
│   ├── encoder.py      # H265EncoderSafe (安全编码)
│   ├── file_info.py    # 文件信息收集
│   ├── validator.py    # 质量验证
│   └── benchmark.py     # 主程序
│
├── roi/
│   ├── motion_detector.py   # 运动检测
│   ├── background_blur.py    # 背景模糊
│   └── roi_encoder.py       # ROIEncoderSafe (安全ROI)
│
├── asvc/               # ASVC 背景估计
├── blue/               # BLUE 背景冻结
├── dedup/              # 安全去重
│   ├── chunker.py      # FastCDC 分块
│   └── index.py       # DedupIndexSafe
│
└── distributed/        # 分布式协调
```

---

## 依赖

| 依赖 | 用途 |
|------|------|
| Python 3.8+ | 运行环境 |
| OpenCV | 视频处理 |
| NumPy | 数组运算 |
| FFmpeg | 视频编解码 |
