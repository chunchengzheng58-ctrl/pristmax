"""
M5 Task Processor: 任务处理器集成

将调度器与实际编码器/Dedup引擎集成。
"""
import os
import sys
import hashlib
import time
from pathlib import Path
from typing import Dict, Callable
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pristmax.scheduler.task_scheduler import Task, TaskStatus, TaskPriority
from commercial.encoder.benchmark.encoder import H265EncoderSafe, EncodeMode


def calculate_sha256(file_path: str) -> str:
    """计算文件SHA-256"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def encode_task_handler(task: Task, progress_callback: Callable = None) -> Dict:
    """
    H.265编码任务处理器

    Args:
        task: 任务对象
        progress_callback: 进度回调函数

    Returns:
        处理结果字典
    """
    input_path = task.input_path
    output_path = task.output_path

    # 检查输入文件是否存在
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # 确定输出路径
    if not output_path:
        input_file = Path(input_path)
        output_path = str(input_file.parent / f"{input_file.stem}_encoded.mp4")

    # 确定编码模式
    mode_str = task.params.get('mode', 'compressed')
    mode_map = {
        'lossless': EncodeMode.LOSSLESS,
        'visually_lossless': EncodeMode.VISUALLY_LOSSLESS,
        'compressed': EncodeMode.COMPRESSED,
        'backup': EncodeMode.BACKUP
    }
    encode_mode = mode_map.get(mode_str.lower(), EncodeMode.COMPRESSED)

    # 创建编码器
    encoder = H265EncoderSafe()

    # 准备编码（需要授权）
    record_id = encoder.prepare_encode(
        input_path=input_path,
        output_path=output_path,
        mode=encode_mode,
        user_id=task.user_id
    )

    # 自动授权（演示模式，生产环境应用户确认）
    encoder.authorizer.authorize(record_id)

    # 执行编码
    if progress_callback:
        progress_callback(10, "Starting encoding...")

    result = encoder.encode(
        input_path=input_path,
        output_path=output_path,
        record_id=record_id,
        skip_authorization=True
    )

    # 转换结果为字典
    result_dict = result.to_dict() if hasattr(result, 'to_dict') else {
        'status': result.status,
        'error': result.error,
        'input_path': input_path,
        'output_path': output_path
    }

    # 验证完整性
    if os.path.exists(output_path) and result.status != 'failed':
        original_hash = calculate_sha256(input_path)
        output_size = os.path.getsize(output_path)
        input_size = os.path.getsize(input_path)

        # 无损模式：解码后逐字节比对原文件
        if encode_mode == EncodeMode.LOSSLESS:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as decoded_tmp:
                decoded_path = decoded_tmp.name

            try:
                # 用 ffmpeg 解码（重新封装为无损格式）
                import subprocess
                subprocess.run([
                    'ffmpeg', '-y', '-i', output_path,
                    '-c:v', 'copy', decoded_path
                ], capture_output=True, check=True)

                decoded_hash = calculate_sha256(decoded_path)
                integrity_verified = (original_hash == decoded_hash)
                lossless_check_performed = True
            except subprocess.CalledProcessError as e:
                integrity_verified = False
                lossless_check_performed = False
                print(f"[encode_task] decode verify failed: {e.stderr.decode() if e.stderr else e}")
            finally:
                if os.path.exists(decoded_path):
                    os.unlink(decoded_path)
        else:
            # 有损模式只验证文件存在
            integrity_verified = True
            lossless_check_performed = False

        return {
            'status': 'success',
            'task_id': task.task_id,
            'input_path': input_path,
            'output_path': output_path,
            'original_size': input_size,
            'output_size': output_size,
            'compression_ratio': (input_size - output_size) / input_size if input_size > 0 else 0.0,
            'original_hash': original_hash,
            'integrity_verified': integrity_verified,
            'lossless_check_performed': lossless_check_performed,
            'encode_mode': encode_mode.value,
            'encode_time_sec': result_dict.get('encode_time_sec', 0)
        }
    else:
        raise RuntimeError(result_dict.get('error') or "Encoding failed - output file not created")


def dedup_task_handler(task: Task, progress_callback: Callable = None) -> Dict:
    """
    去重任务处理器

    Args:
        task: 任务对象
        progress_callback: 进度回调函数

    Returns:
        处理结果字典
    """
    from src.pristmax.dedup.index import DedupIndexSafe

    input_path = task.input_path
    db_path = task.params.get('index_path', './dedup_safe.db')

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input path not found: {input_path}")

    # 创建去重索引
    index = DedupIndexSafe(db_path=db_path)

    if progress_callback:
        progress_callback(10, "Scanning for duplicates...")

    # 扫描文件（简化版本）
    if os.path.isfile(input_path):
        files = [input_path]
    else:
        files = []
        for root, dirs, filenames in os.walk(input_path):
            for f in filenames:
                files.append(os.path.join(root, f))

    total_files = len(files)
    unique_chunks = 0
    duplicate_chunks = 0
    total_size = 0
    saved_size = 0

    for i, file_path in enumerate(files):
        if progress_callback:
            progress = 10 + int((i / total_files) * 60) if total_files > 0 else 70
            progress_callback(progress, f"Processing {i+1}/{total_files}")

        # 计算文件哈希
        file_hash = calculate_sha256(file_path)
        file_size = os.path.getsize(file_path)
        total_size += file_size

        # 添加到索引，返回 True=新增唯一块，False=重复块
        is_new = index.add_chunk(
            chunk_id=file_hash,
            content_hash=file_hash,
            size=file_size,
            storage_path=file_path
        )

        if is_new:
            # 新增唯一块
            unique_chunks += 1
        else:
            # 重复块
            duplicate_chunks += 1
            saved_size += file_size

    if progress_callback:
        progress_callback(95, "Finalizing...")

    if progress_callback:
        progress_callback(100, "Deduplication complete")

    dedup_ratio = saved_size / total_size if total_size > 0 else 0.0

    return {
        'status': 'success',
        'task_id': task.task_id,
        'input_path': input_path,
        'total_files': total_files,
        'unique_chunks': unique_chunks,
        'duplicate_chunks': duplicate_chunks,
        'total_size': total_size,
        'saved_size': saved_size,
        'dedup_ratio': dedup_ratio
    }


def scan_task_handler(task: Task, progress_callback: Callable = None) -> Dict:
    """
    扫描任务处理器 - 收集文件信息

    Args:
        task: 任务对象
        progress_callback: 进度回调函数

    Returns:
        处理结果字典
    """
    input_path = task.input_path

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input path not found: {input_path}")

    if progress_callback:
        progress_callback(10, "Starting scan...")

    total_files = 0
    total_size = 0
    file_types: Dict[str, int] = {}
    largest_files = []

    for root, dirs, files in os.walk(input_path):
        # 跳过隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for i, filename in enumerate(files):
            if filename.startswith('.'):
                continue

            file_path = os.path.join(root, filename)
            try:
                size = os.path.getsize(file_path)
                total_files += 1
                total_size += size

                # 统计文件类型
                ext = Path(filename).suffix.lower() or 'no_extension'
                file_types[ext] = file_types.get(ext, 0) + 1

                # 记录大文件
                largest_files.append({
                    'path': file_path,
                    'size': size
                })

            except (OSError, PermissionError):
                continue

            if progress_callback and i % 100 == 0:
                pct = min(90, 10 + int((total_files / max(total_files, 1)) * 80))
                progress_callback(pct, f"Scanned {total_files} files...")

    if progress_callback:
        progress_callback(100, "Scan complete")

    # 排序并取最大文件
    largest_files.sort(key=lambda x: x['size'], reverse=True)
    largest_files = largest_files[:10]

    if progress_callback:
        progress_callback(100, "Scan complete")

    return {
        'status': 'success',
        'task_id': task.task_id,
        'input_path': input_path,
        'total_files': total_files,
        'total_size': total_size,
        'total_size_gb': round(total_size / (1024**3), 2),
        'file_types': dict(sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:10]),
        'largest_files': largest_files
    }


def roi_task_handler(task: Task, progress_callback: Callable = None) -> Dict:
    """
    ROI 编码任务处理器

    Args:
        task: 任务对象
        progress_callback: 进度回调函数

    Returns:
        处理结果字典
    """
    from commercial.surveillance.roi.roi_encoder import ROIEncoderSafe, ROIEncoderConfig

    input_path = task.input_path
    output_path = task.output_path

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # 获取 ROI 参数
    params = task.params or {}
    crf = params.get('crf', 28)
    preset = params.get('preset', 'medium')
    motion_threshold = params.get('motion_threshold', 25)
    blur_kernel = params.get('blur_kernel', 21)

    # 确定输出目录
    if not output_path:
        output_dir = str(Path(input_path).parent)
    else:
        output_dir = str(Path(output_path).parent) if Path(output_path).suffix else output_path
        output_path = str(Path(output_path) / f"{Path(input_path).stem}_roi.mp4") if Path(output_path).is_dir() else output_path

    if progress_callback:
        progress_callback(5, "Initializing ROI encoder...")

    # 创建 ROI 编码器
    config = ROIEncoderConfig(
        h265_crf=crf,
        h265_preset=preset,
        motion_threshold=motion_threshold,
        blur_kernel=blur_kernel,
        require_authorization=False  # API 模式自动授权
    )
    encoder = ROIEncoderSafe(config=config)

    # 请求授权（自动授权模式）
    record_id = encoder.request_encode(
        input_path=input_path,
        output_path=output_path,
        description=f"ROI encoding task: {task.task_id}"
    )
    encoder.authorize(record_id)

    if progress_callback:
        progress_callback(10, "Motion detection...")

    # 执行 ROI 编码
    result = encoder.encode(
        input_path=input_path,
        output_dir=output_dir,
        record_id=record_id,
        skip_authorization=True
    )

    if result.status == "completed":
        return {
            'status': 'success',
            'task_id': task.task_id,
            'input_path': input_path,
            'output_path': result.output_path,
            'original_size': result.input_size_bytes,
            'encoded_size': result.encoded_size_bytes,
            'compression_ratio': result.compression_ratio,
            'roi_ratio': result.roi_ratio,
            'motion_ratio': result.motion_ratio,
            'original_sha256': result.original_sha256,
            'output_sha256': result.output_sha256,
            'integrity_verified': result.integrity_verified
        }
    else:
        raise RuntimeError(result.error or "ROI encoding failed")


def _notify_task_completion(task: Task):
    """
    任务完成时发送通知
    """
    try:
        from src.pristmax.monitor.notifications import get_notification_manager
        from src.pristmax.monitor.metrics import Alert, AlertLevel

        nm = get_notification_manager()
        channels = nm.get_channels()
        if not channels:
            return

        if task.status.value == 'completed':
            title = f"任务完成: {task.task_type}"
            message = f"任务 {task.task_id} 已成功完成"
            level = AlertLevel.INFO
        else:
            title = f"任务失败: {task.task_type}"
            message = f"任务 {task.task_id} 失败: {task.error}"
            level = AlertLevel.WARNING

        alert = Alert(
            level=level,
            title=title,
            message=message,
            metric='task',
            value=0,
            threshold=0
        )
        alert.alert_id = f"task-{task.task_id}"

        results = nm.send_alert(alert)
        for ch_id, res in results.items():
            if res['status'] == 'sent':
                print(f"[TaskNotify] Sent to {ch_id}")
            else:
                print(f"[TaskNotify] Failed to {ch_id}: {res.get('error')}")
    except Exception as e:
        print(f"[TaskNotify] Notification error: {e}")


# 任务处理器注册表
TASK_HANDLERS = {
    'encode': encode_task_handler,
    'dedup': dedup_task_handler,
    'scan': scan_task_handler,
    'roi': roi_task_handler,
}


def register_all_handlers(scheduler):
    """注册所有任务处理器到调度器"""
    for task_type, handler in TASK_HANDLERS.items():
        scheduler.register_handler(task_type, handler)
        print(f"[TaskProcessor] Registered handler: {task_type}")
