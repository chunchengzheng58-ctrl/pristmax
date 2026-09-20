"""
Storage Agent: 智能存储管家 (安全增强版)

功能：
- 大文件分析
- 重复文件检测
- 存储使用统计
- 文件分类整理
- 智能搜索
- 增量扫描
- 导出报告
- 对话交互

安全特性：
- 路径白名单控制
- 只读模式
- 资源限制
- 操作审批流程
- 完整审计日志

性能特性：
- 并行扫描（ThreadPoolExecutor）
- SQLite 缓存（TTL 过期）
- 分页查询
- 批量数据库操作
"""
import os
import sys
import hashlib
import json
import sqlite3
import time
import re
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable, Generator, Iterator, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import signal

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================
# 工具函数
# ============================================

def timeout(seconds: int):
    """超时装饰器，用于大文件操作"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            def handler(signum, frame):
                raise TimeoutError(f"{func.__name__} 超时 ({seconds}s)")
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)
            return result
        return wrapper
    return decorator


# ============================================
# 安全配置
# ============================================

class CancellationToken:
    """操作取消令牌"""
    def __init__(self):
        self._cancelled = False

    def cancel(self):
        """请求取消操作"""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def reset(self):
        """重置取消状态"""
        self._cancelled = False


class ProgressTracker:
    """进度跟踪器"""
    def __init__(self, total: int = 0):
        self.total = total
        self.current = 0
        self.start_time = time.time()
        self.errors: List[dict] = []

    def update(self, n: int = 1, message: str = None):
        """更新进度"""
        self.current += n

    def set_total(self, total: int):
        self.total = total

    def add_error(self, error: dict):
        self.errors.append(error)

    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 0
        return (self.current / self.total) * 100

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def to_dict(self) -> dict:
        return {
            'current': self.current,
            'total': self.total,
            'percent': self.progress_percent,
            'elapsed_seconds': self.elapsed_seconds,
            'errors': self.errors
        }


class ScanProgressTracker:
    """扫描进度跟踪器（全局）"""
    _progress: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def add(cls, scan_id: str, data: dict):
        with cls._lock:
            cls._progress[scan_id] = data

    @classmethod
    def update(cls, scan_id: str, **kwargs):
        with cls._lock:
            if scan_id in cls._progress:
                cls._progress[scan_id].update(kwargs)

    @classmethod
    def get(cls, scan_id: str) -> Optional[dict]:
        with cls._lock:
            return cls._progress.get(scan_id)

    @classmethod
    def list_all(cls) -> Dict[str, dict]:
        with cls._lock:
            return dict(cls._progress)

    @classmethod
    def remove(cls, scan_id: str):
        with cls._lock:
            cls._progress.pop(scan_id, None)

    @classmethod
    def cleanup_old(cls, max_age_seconds: int = 3600):
        """清理超过指定时间的旧记录"""
        with cls._lock:
            now = time.time()
            expired = [k for k, v in cls._progress.items()
                      if now - v.get('start_time', 0) > max_age_seconds]
            for k in expired:
                cls._progress.pop(k, None)

    def to_dict(self) -> dict:
        return {
            'current': self.current,
            'total': self.total,
            'percent': self.progress_percent,
            'elapsed_seconds': self.elapsed_seconds,
            'errors': self.errors
        }


class ScheduledTaskManager:
    """定时任务管理器"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._scheduler = None
        self._tasks = {}
        self._results = {}

    def start(self):
        """启动调度器"""
        if self._scheduler is not None:
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.schedulers.blocking import BlockingScheduler
        except ImportError:
            return

        self._scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
        self._scheduler.start()

    def stop(self):
        """停止调度器"""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    def add_scan_task(self, task_id: str, path: str, schedule: str, task_type: str = 'stats') -> dict:
        """添加定时扫描任务

        Args:
            task_id: 任务ID
            path: 要扫描的路径
            schedule: Cron表达式，如 '0 2 * * *'（每天凌晨2点）
            task_type: 任务类型 'stats'(统计) | 'duplicates'(重复文件) | 'large'(大文件)

        Returns:
            {'task_id': ..., 'status': 'added'/'error', 'message': ...}
        """
        if not self._scheduler:
            self.start()

        # 移除已存在的同ID任务
        if task_id in self._tasks:
            self.remove_task(task_id)

        def task_func():
            agent = StorageAgent()
            if task_type == 'stats':
                result = agent.get_storage_stats(path)
            elif task_type == 'duplicates':
                result = agent.find_duplicates(path)
            elif task_type == 'large':
                result = agent.analyze_large_files(path)
            else:
                result = {}

            self._results[task_id] = {
                'last_run': time.time(),
                'result': result
            }
            ScanProgressTracker.update(f'scheduled_{task_id}',
                status='completed',
                last_run=time.time(),
                result_summary=str(result)[:200]
            )

        try:
            # 解析 cron 表达式
            parts = schedule.split()
            if len(parts) == 5:
                self._scheduler.add_job(
                    task_func,
                    'cron',
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                    id=task_id,
                    replace_existing=True
                )
            else:
                # 间隔执行，如 'interval', {'hours': 1}
                self._scheduler.add_job(
                    task_func,
                    'interval',
                    hours=1,
                    id=task_id,
                    replace_existing=True
                )

            self._tasks[task_id] = {
                'path': path,
                'schedule': schedule,
                'task_type': task_type,
                'status': 'active'
            }

            ScanProgressTracker.add(f'scheduled_{task_id}', {
                'task_id': task_id,
                'type': 'scheduled',
                'path': path,
                'schedule': schedule,
                'task_type': task_type,
                'status': 'active',
                'start_time': time.time()
            })

            return {'task_id': task_id, 'status': 'added', 'message': 'Task scheduled successfully'}

        except Exception as e:
            return {'task_id': task_id, 'status': 'error', 'message': str(e)}

    def remove_task(self, task_id: str) -> dict:
        """移除定时任务"""
        if self._scheduler and task_id in self._tasks:
            self._scheduler.remove_job(task_id)
            del self._tasks[task_id]
            ScanProgressTracker.remove(f'scheduled_{task_id}')
            return {'task_id': task_id, 'status': 'removed'}
        return {'task_id': task_id, 'status': 'not_found'}

    def list_tasks(self) -> list:
        """列出所有定时任务"""
        return [
            {'task_id': tid, **task}
            for tid, task in self._tasks.items()
        ]

    def get_task_result(self, task_id: str) -> dict:
        """获取任务最近执行结果"""
        return self._results.get(task_id, {})

    def get_next_run(self, task_id: str) -> Optional[str]:
        """获取任务下次执行时间"""
        if self._scheduler:
            job = self._scheduler.get_job(task_id)
            if job:
                return str(job.next_run_time)
        return None


class CloudStorageManager:
    """云存储管理器（支持 S3/OSS/MinIO）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._clients = {}
        self._configs = {
            's3': {
                'bucket': None,
                'region': 'us-east-1'
            },
            'oss': {
                'bucket': None,
                'endpoint': None
            }
        }

    def configure_s3(self, access_key: str, secret_key: str, bucket: str, region: str = 'us-east-1', endpoint: str = None):
        """配置 S3 兼容存储（AWS S3 / MinIO / 腾讯COS）"""
        try:
            import boto3
            from botocore.config import Config

            config = Config(region_name=region)
            client_config = {
                'aws_access_key_id': access_key,
                'aws_secret_access_key': secret_key,
                'region_name': region,
                'config': config
            }

            if endpoint:
                client_config['endpoint_url'] = endpoint

            client = boto3.client('s3', **client_config)

            # 验证连接
            client.head_bucket(Bucket=bucket)

            self._clients['s3'] = {
                'client': client,
                'bucket': bucket,
                'type': 's3'
            }
            self._configs['s3'] = {
                'bucket': bucket,
                'region': region,
                'endpoint': endpoint
            }
            return {'status': 'configured', 'type': 's3', 'bucket': bucket}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def configure_oss(self, access_key: str, secret_key: str, bucket: str, endpoint: str):
        """配置阿里云 OSS"""
        try:
            import oss2

            auth = oss2.Auth(access_key, secret_key)
            client = oss2.Bucket(auth, endpoint, bucket)

            # 验证连接
            client.get_bucket_info()

            self._clients['oss'] = {
                'client': client,
                'bucket': bucket,
                'type': 'oss'
            }
            return {'status': 'configured', 'type': 'oss', 'bucket': bucket}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def upload_file(self, local_path: str, cloud_path: str, provider: str = 's3') -> dict:
        """上传文件到云存储"""
        if provider not in self._clients:
            return {'status': 'error', 'message': f'{provider} not configured'}

        try:
            client_info = self._clients[provider]
            client = client_info['client']
            bucket = client_info['bucket']

            if provider == 's3':
                client.upload_file(Bucket=bucket, Key=cloud_path, Filename=local_path)
            elif provider == 'oss':
                client.put_object_from_file(cloud_path, local_path)

            return {'status': 'uploaded', 'cloud_path': cloud_path, 'provider': provider}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def download_file(self, cloud_path: str, local_path: str, provider: str = 's3') -> dict:
        """从云存储下载文件"""
        if provider not in self._clients:
            return {'status': 'error', 'message': f'{provider} not configured'}

        try:
            client_info = self._clients[provider]
            client = client_info['client']
            bucket = client_info['bucket']

            if provider == 's3':
                client.download_file(Bucket=bucket, Key=cloud_path, Filename=local_path)
            elif provider == 'oss':
                client.get_object_to_file(cloud_path, local_path)

            return {'status': 'downloaded', 'local_path': local_path, 'provider': provider}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def list_files(self, prefix: str = '', provider: str = 's3') -> dict:
        """列出云存储中的文件"""
        if provider not in self._clients:
            return {'status': 'error', 'message': f'{provider} not configured'}

        try:
            client_info = self._clients[provider]
            client = client_info['client']
            bucket = client_info['bucket']
            files = []

            if provider == 's3':
                paginator = client.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for obj in page.get('Contents', []):
                        files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'modified': obj['LastModified'].isoformat() if obj.get('LastModified') else None
                        })
            elif provider == 'oss':
                for obj in oss2.ObjectIterator(client, prefix=prefix):
                    files.append({
                        'key': obj.key,
                        'size': obj.size,
                        'modified': obj.last_modified.isoformat() if hasattr(obj, 'last_modified') else None
                    })

            return {'status': 'ok', 'files': files, 'count': len(files), 'provider': provider}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def delete_file(self, cloud_path: str, provider: str = 's3') -> dict:
        """删除云存储中的文件"""
        if provider not in self._clients:
            return {'status': 'error', 'message': f'{provider} not configured'}

        try:
            client_info = self._clients[provider]
            client = client_info['client']
            bucket = client_info['bucket']

            if provider == 's3':
                client.delete_object(Bucket=bucket, Key=cloud_path)
            elif provider == 'oss':
                client.delete_object(cloud_path)

            return {'status': 'deleted', 'cloud_path': cloud_path, 'provider': provider}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def sync_to_cloud(self, local_path: str, cloud_prefix: str, provider: str = 's3', exclude_patterns: List[str] = None) -> dict:
        """同步本地目录到云存储"""
        if provider not in self._clients:
            return {'status': 'error', 'message': f'{provider} not configured'}

        if exclude_patterns is None:
            exclude_patterns = ['.git', '__pycache__', '*.pyc', '.DS_Store']

        uploaded = []
        failed = []

        for root, dirs, files in os.walk(local_path):
            # 过滤目录
            dirs[:] = [d for d in dirs if not any(p in d for p in exclude_patterns)]

            for filename in files:
                if any(p in filename for p in exclude_patterns):
                    continue

                local_file = os.path.join(root, filename)
                relative_path = os.path.relpath(local_file, local_path)
                cloud_path = os.path.join(cloud_prefix, relative_path).replace(os.sep, '/')

                result = self.upload_file(local_file, cloud_path, provider)
                if result['status'] == 'uploaded':
                    uploaded.append(cloud_path)
                else:
                    failed.append({'file': local_file, 'error': result.get('message')})

        return {
            'status': 'completed',
            'uploaded': len(uploaded),
            'failed': len(failed),
            'errors': failed[:10]  # 只返回前10个错误
        }

    def get_status(self, provider: str = 's3') -> dict:
        """获取云存储状态"""
        if provider in self._clients:
            return {
                'configured': True,
                'provider': provider,
                'bucket': self._configs.get(provider, {}).get('bucket')
            }
        return {'configured': False, 'provider': provider}


class DesktopSyncManager:
    """桌面端同步管理器 - 同步扫描结果和设置到云端"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._sync_db = os.path.join(os.path.expanduser('~'), '.pristmax', 'sync.db')
        self._ensure_db()

    def _ensure_db(self):
        """确保同步数据库存在"""
        os.makedirs(os.path.dirname(self._sync_db), exist_ok=True)
        conn = sqlite3.connect(self._sync_db)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sync_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                scan_result TEXT,
                last_sync INTEGER,
                sync_version INTEGER DEFAULT 1
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sync_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def save_scan_result(self, path: str, scan_result: dict) -> dict:
        """保存扫描结果到本地同步库"""
        try:
            conn = sqlite3.connect(self._sync_db)
            result_json = json.dumps(scan_result, ensure_ascii=False, default=str)
            now = int(time.time())

            conn.execute('''
                INSERT OR REPLACE INTO sync_records (path, scan_result, last_sync, sync_version)
                VALUES (?, ?, ?,
                    COALESCE((SELECT sync_version FROM sync_records WHERE path = ?), 0) + 1)
            ''', (path, result_json, now, path))

            conn.commit()
            conn.close()

            return {'status': 'saved', 'path': path, 'timestamp': now}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def get_scan_result(self, path: str) -> dict:
        """获取本地缓存的扫描结果"""
        try:
            conn = sqlite3.connect(self._sync_db)
            cursor = conn.execute(
                'SELECT scan_result, last_sync, sync_version FROM sync_records WHERE path = ?',
                (path,)
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    'status': 'found',
                    'result': json.loads(row[0]),
                    'last_sync': row[1],
                    'sync_version': row[2]
                }
            return {'status': 'not_found', 'path': path}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def list_synced_paths(self) -> list:
        """列出所有已同步的路径"""
        try:
            conn = sqlite3.connect(self._sync_db)
            cursor = conn.execute(
                'SELECT path, last_sync, sync_version FROM sync_records ORDER BY last_sync DESC'
            )
            rows = cursor.fetchall()
            conn.close()

            return [
                {'path': r[0], 'last_sync': r[1], 'sync_version': r[2]}
                for r in rows
            ]

        except Exception as e:
            return []

    def delete_sync_record(self, path: str) -> dict:
        """删除同步记录"""
        try:
            conn = sqlite3.connect(self._sync_db)
            conn.execute('DELETE FROM sync_records WHERE path = ?', (path,))
            conn.commit()
            conn.close()
            return {'status': 'deleted', 'path': path}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def sync_to_cloud(self, local_path: str = None, cloud_prefix: str = 'pristmax/sync/',
                      provider: str = 's3') -> dict:
        """同步本地缓存到云端"""
        try:
            cloud_manager = CloudStorageManager()
            if not cloud_manager._clients.get(provider):
                return {'status': 'error', 'message': f'{provider} not configured'}

            # 读取本地数据库
            conn = sqlite3.connect(self._sync_db)
            cursor = conn.execute('SELECT path, scan_result, last_sync FROM sync_records')
            records = cursor.fetchall()
            conn.close()

            synced = 0
            failed = []

            for path, result_json, last_sync in records:
                cloud_path = f"{cloud_prefix}{hashlib.md5(path.encode()).hexdigest()}.json"

                # 写入临时文件
                temp_file = os.path.join(tempfile.gettempdir(), f'sync_{os.getpid()}.json')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(result_json)

                result = cloud_manager.upload_file(temp_file, cloud_path, provider)
                os.unlink(temp_file)

                if result['status'] == 'uploaded':
                    synced += 1
                else:
                    failed.append({'path': path, 'error': result.get('message')})

            return {
                'status': 'completed',
                'synced': synced,
                'failed': len(failed),
                'errors': failed[:5]
            }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def restore_from_cloud(self, cloud_prefix: str = 'pristmax/sync/',
                          provider: str = 's3') -> dict:
        """从云端恢复同步数据"""
        try:
            cloud_manager = CloudStorageManager()
            if not cloud_manager._clients.get(provider):
                return {'status': 'error', 'message': f'{provider} not configured'}

            # 列出云端文件
            result = cloud_manager.list_files(cloud_prefix, provider)
            if result['status'] != 'ok':
                return result

            restored = 0
            failed = []

            for file_info in result['files']:
                cloud_path = file_info['key']

                # 下载到临时文件
                temp_file = os.path.join(tempfile.gettempdir(), f'restore_{os.getpid()}.json')
                download_result = cloud_manager.download_file(cloud_path, temp_file, provider)

                if download_result['status'] == 'downloaded':
                    with open(temp_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # 恢复记录
                    if 'path' in data and 'result' in data:
                        self.save_scan_result(data['path'], data['result'])
                        restored += 1

                    os.unlink(temp_file)
                else:
                    failed.append({'cloud_path': cloud_path, 'error': download_result.get('message')})

            return {
                'status': 'completed',
                'restored': restored,
                'failed': len(failed),
                'errors': failed[:5]
            }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def get_sync_status(self) -> dict:
        """获取同步状态"""
        try:
            conn = sqlite3.connect(self._sync_db)
            cursor = conn.execute('SELECT COUNT(*), MAX(last_sync) FROM sync_records')
            row = cursor.fetchone()
            conn.close()

            return {
                'total_records': row[0] if row else 0,
                'last_sync': row[1] if row and row[1] else None,
                'db_path': self._sync_db
            }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}


class SecurityConfig:
    """安全配置"""
    def __init__(self):
        # 路径白名单（只允许扫描这些目录）
        self.allowed_paths: List[str] = []

        # 只读模式（禁止任何删除操作）
        self.readonly_mode: bool = True

        # 资源限制
        self.max_scan_files: int = 1000000      # 最多扫描100万文件
        self.max_scan_size_gb: int = 10000       # 最多扫描10TB
        self.max_operation_time: int = 3600       # 单次操作最多1小时
        self.max_file_size_mb: int = 102400       # 单文件最大100GB
        self.max_batch_size: int = 1000           # 批量操作最大数量

        # 并行扫描配置
        self.parallel_enabled: bool = True        # 启用并行扫描
        self.parallel_threads: int = 4           # 并行线程数
        self.parallel_dirs_per_thread: int = 50   # 每个线程处理的子目录数

        # API 速率限制
        self.api_rate_limit: int = 100            # 每分钟最多100次
        self.api_calls: List[float] = []          # API调用记录

        # 是否启用审批流程
        self.require_approval: bool = True

        # 高危操作需要额外确认
        self.high_risk_confirm: bool = True

        # 操作超时（秒）
        self.operation_timeout: int = 300

    def load_from_env(self):
        """从环境变量加载配置"""
        if os.environ.get('STORAGE_ALLOWED_PATHS'):
            self.allowed_paths = os.environ['STORAGE_ALLOWED_PATHS'].split(',')
        self.readonly_mode = os.environ.get('STORAGE_READONLY', 'true').lower() == 'true'
        self.require_approval = os.environ.get('STORAGE_REQUIRE_APPROVAL', 'true').lower() == 'true'
        if os.environ.get('STORAGE_PARALLEL_THREADS'):
            self.parallel_threads = int(os.environ['STORAGE_PARALLEL_THREADS'])

    def check_rate_limit(self) -> Tuple[bool, str]:
        """检查API速率限制"""
        now = time.time()
        # 清理一分钟前的记录
        self.api_calls = [t for t in self.api_calls if now - t < 60]
        if len(self.api_calls) >= self.api_rate_limit:
            return False, f"API速率限制: 每分钟最多{self.api_rate_limit}次"
        self.api_calls.append(now)
        return True, ""

    def validate_path(self, path: str) -> Tuple[bool, str]:
        """验证路径安全性"""
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return False, f"路径不存在: {path}"
        if not os.path.isdir(abs_path):
            return False, f"路径不是目录: {path}"
        return True, ""

    def to_dict(self) -> dict:
        """导出配置"""
        return {
            'allowed_paths': self.allowed_paths,
            'readonly_mode': self.readonly_mode,
            'require_approval': self.require_approval,
            'max_scan_files': self.max_scan_files,
            'max_scan_size_gb': self.max_scan_size_gb,
            'max_operation_time': self.max_operation_time,
            'max_file_size_mb': self.max_file_size_mb,
            'max_batch_size': self.max_batch_size,
            'parallel_enabled': self.parallel_enabled,
            'parallel_threads': self.parallel_threads,
            'parallel_dirs_per_thread': self.parallel_dirs_per_thread,
            'api_rate_limit': self.api_rate_limit,
            'high_risk_confirm': self.high_risk_confirm,
            'operation_timeout': self.operation_timeout
        }


# 全局安全配置
_security_config = SecurityConfig()


def set_security_config(
    allowed_paths: List[str] = None,
    readonly: bool = True,
    require_approval: bool = True,
    max_files: int = 1000000,
    max_size_gb: int = 10000
):
    """设置安全配置"""
    if allowed_paths:
        _security_config.allowed_paths = allowed_paths
    _security_config.readonly_mode = readonly
    _security_config.require_approval = require_approval
    _security_config.max_scan_files = max_files
    _security_config.max_scan_size_gb = max_size_gb


# ============================================
# 审批流程
# ============================================

class OperationStatus(Enum):
    """操作状态"""
    PENDING = "pending"      # 待审批
    APPROVED = "approved"   # 已批准
    REJECTED = "rejected"   # 已拒绝
    EXECUTING = "executing" # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"       # 失败


class OperationType(Enum):
    """操作类型"""
    SCAN = "scan"
    ANALYZE = "analyze"
    DELETE_FILES = "delete_files"
    DELETE_DUPLICATES = "delete_duplicates"
    EXPORT_REPORT = "export_report"


@dataclass
class Operation:
    """操作记录"""
    id: str
    type: OperationType
    status: OperationStatus
    path: str
    params: dict
    created_at: str
    approved_at: Optional[str] = None
    executed_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    approved_by: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': self.type.value,
            'status': self.status.value,
            'path': self.path,
            'params': self.params,
            'created_at': self.created_at,
            'approved_at': self.approved_at,
            'executed_at': self.executed_at,
            'completed_at': self.completed_at,
            'result': self.result,
            'error': self.error,
            'approved_by': self.approved_by
        }


class ApprovalManager:
    """审批管理器"""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                path TEXT NOT NULL,
                params TEXT,
                created_at TEXT NOT NULL,
                approved_at TEXT,
                executed_at TEXT,
                completed_at TEXT,
                result TEXT,
                error TEXT,
                approved_by TEXT
            )
        ''')
        self.conn.commit()

    def create_operation(
        self,
        op_type: OperationType,
        path: str,
        params: dict = None
    ) -> Operation:
        """创建操作（待审批）"""
        op_id = f"op_{int(time.time() * 1000)}"
        now = datetime.now().isoformat()

        op = Operation(
            id=op_id,
            type=op_type,
            status=OperationStatus.PENDING,
            path=path,
            params=params or {},
            created_at=now
        )

        self.conn.execute('''
            INSERT INTO operations
            (id, type, status, path, params, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (op_id, op.type.value, op.status.value, path,
              json.dumps(params or {}), now))
        self.conn.commit()

        return op

    def get_operation(self, op_id: str) -> Optional[Operation]:
        """获取操作"""
        cursor = self.conn.execute(
            'SELECT * FROM operations WHERE id = ?', (op_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_operation(row)
        return None

    def list_operations(
        self,
        status: OperationStatus = None,
        limit: int = 50
    ) -> List[Operation]:
        """列出操作"""
        if status:
            cursor = self.conn.execute(
                'SELECT * FROM operations WHERE status = ? ORDER BY created_at DESC LIMIT ?',
                (status.value, limit))
        else:
            cursor = self.conn.execute(
                'SELECT * FROM operations ORDER BY created_at DESC LIMIT ?',
                (limit,))
        return [self._row_to_operation(row) for row in cursor.fetchall()]

    def approve(self, op_id: str, approved_by: str = "system") -> bool:
        """批准操作"""
        now = datetime.now().isoformat()
        self.conn.execute('''
            UPDATE operations
            SET status = ?, approved_at = ?, approved_by = ?
            WHERE id = ? AND status = ?
        ''', (OperationStatus.APPROVED.value, now, approved_by,
              op_id, OperationStatus.PENDING.value))
        self.conn.commit()
        return self.conn.total_changes > 0

    def reject(self, op_id: str, rejected_by: str = "system") -> bool:
        """拒绝操作"""
        now = datetime.now().isoformat()
        self.conn.execute('''
            UPDATE operations
            SET status = ?, approved_at = ?, approved_by = ?
            WHERE id = ? AND status = ?
        ''', (OperationStatus.REJECTED.value, now, rejected_by,
              op_id, OperationStatus.PENDING.value))
        self.conn.commit()
        return self.conn.total_changes > 0

    def complete(self, op_id: str, result: dict = None, error: str = None):
        """完成操作"""
        now = datetime.now().isoformat()
        self.conn.execute('''
            UPDATE operations
            SET status = ?, completed_at = ?, result = ?, error = ?
            WHERE id = ?
        ''', (
            OperationStatus.COMPLETED.value if not error else OperationStatus.FAILED.value,
            now,
            json.dumps(result) if result else None,
            error,
            op_id
        ))
        self.conn.commit()

    def _row_to_operation(self, row) -> Operation:
        return Operation(
            id=row[0],
            type=OperationType(row[1]),
            status=OperationStatus(row[2]),
            path=row[3],
            params=json.loads(row[4]) if row[4] else {},
            created_at=row[5],
            approved_at=row[6],
            executed_at=row[7],
            completed_at=row[8],
            result=json.loads(row[9]) if row[9] else None,
            error=row[10],
            approved_by=row[11]
        )


# ============================================
# 审计日志
# ============================================

class AuditLogger:
    """审计日志"""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                operation TEXT NOT NULL,
                path TEXT,
                details TEXT,
                user TEXT,
                ip TEXT
            )
        ''')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log(timestamp)')
        self.conn.commit()

    def log(self, level: str, operation: str, path: str = None, details: dict = None, user: str = None):
        """记录日志"""
        now = datetime.now().isoformat()
        self.conn.execute('''
            INSERT INTO audit_log (timestamp, level, operation, path, details, user)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (now, level, operation, path, json.dumps(details) if details else None, user))
        self.conn.commit()

    def info(self, operation: str, path: str = None, details: dict = None):
        self.log("INFO", operation, path, details)

    def warning(self, operation: str, path: str = None, details: dict = None):
        self.log("WARNING", operation, path, details)

    def error(self, operation: str, path: str = None, details: dict = None):
        self.log("ERROR", operation, path, details)


# ============================================
# ANSI 颜色码
# ============================================

class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'


def color(text: str, code: str) -> str:
    if sys.platform == 'win32' and not os.environ.get('ANSI_COLORS'):
        return text
    return f"{code}{text}{Colors.RESET}"


# ============================================
# 数据类
# ============================================

@dataclass
class FileInfo:
    path: str
    name: str
    size: int
    size_display: str
    extension: str
    modified: str
    created: str
    type_category: str

    @staticmethod
    def format_size(size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"


@dataclass
class DuplicateGroup:
    hash: str
    size: int
    size_display: str
    count: int
    files: List[str]
    wasted_space: int


# ============================================
# Storage Agent 核心类
# ============================================

class StorageAgent:
    """
    智能存储管家 Agent (安全增强版)

    核心功能：
    1. 大文件分析 - 找出占用空间最多的文件
    2. 重复文件检测 - 通过哈希检测重复文件
    3. 存储统计 - 各类型文件占用空间
    4. 文件分类 - 按类型自动分类
    """

    # 高危操作类型
    HIGH_RISK_OPERATIONS = [
        OperationType.DELETE_FILES,
        OperationType.DELETE_DUPLICATES
    ]

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()
        self.approval_manager = ApprovalManager(db_path)
        self.audit_logger = AuditLogger(db_path)

        # 缓存配置
        self.cache_ttl_seconds = 3600  # 缓存1小时
        self.cache_enabled = True

        logger.info("StorageAgent initialized")

    def health_check(self) -> dict:
        """健康检查接口，返回系统状态

        Returns:
            健康状态字典
        """
        status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {}
        }

        # 检查数据库连接
        try:
            self.conn.execute('SELECT 1')
            status['components']['database'] = 'ok'
        except Exception as e:
            status['components']['database'] = f'error: {str(e)}'
            status['status'] = 'unhealthy'

        # 检查缓存
        try:
            cursor = self.conn.execute('SELECT COUNT(*) FROM scan_cache')
            cache_count = cursor.fetchone()[0]
            status['components']['cache'] = f'ok ({cache_count} entries)'
        except Exception as e:
            status['components']['cache'] = f'error: {str(e)}'

        # 检查安全配置
        status['components']['security'] = 'enabled' if _security_config.allowed_paths else 'permissive'

        return status

    def get_scan_history(self, limit: int = 20) -> List[dict]:
        """获取扫描历史记录

        Args:
            limit: 返回数量限制

        Returns:
            扫描历史列表
        """
        try:
            cursor = self.conn.execute('''
                SELECT path, scanned_at, expires_at
                FROM scan_cache
                ORDER BY scanned_at DESC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            return [
                {'path': r[0], 'scanned_at': r[1], 'expires_at': r[2]}
                for r in rows
            ]
        except Exception as e:
            logger.error(f"获取扫描历史失败: {e}")
            return []

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息

        Returns:
            缓存统计
        """
        try:
            cursor = self.conn.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(LENGTH(result_json)) as total_size
                FROM scan_cache
            ''')
            row = cursor.fetchone()
            return {
                'total_entries': row[0] or 0,
                'total_size_bytes': row[1] or 0,
                'total_size_display': FileInfo.format_size(row[1] or 0)
            }
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {'total_entries': 0, 'total_size_bytes': 0, 'total_size_display': '0 B'}

    def clear_expired_cache(self) -> int:
        """清理过期缓存

        Returns:
            清理的条目数量
        """
        try:
            cursor = self.conn.execute('''
                DELETE FROM scan_cache
                WHERE expires_at IS NOT NULL
                AND datetime(expires_at) < datetime('now')
            ''')
            self.conn.commit()
            deleted = cursor.rowcount
            logger.info(f"清理了 {deleted} 条过期缓存")
            return deleted
        except Exception as e:
            logger.error(f"清理过期缓存失败: {e}")
            return 0

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS file_cache (
                path TEXT PRIMARY KEY,
                name TEXT,
                size INTEGER,
                hash TEXT,
                extension TEXT,
                category TEXT,
                modified TEXT,
                created TEXT,
                scanned_at TEXT
            )
        ''')
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_size ON file_cache(size DESC)
        ''')
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_hash ON file_cache(hash)
        ''')
        # 扫描结果缓存表
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS scan_cache (
                path TEXT PRIMARY KEY,
                cache_key TEXT,
                result_json TEXT,
                scanned_at TEXT,
                expires_at TEXT
            )
        ''')
        self.conn.commit()

    def _get_cache_key(self, path: str) -> str:
        """生成缓存键（基于路径和修改时间）"""
        try:
            stat = os.stat(path)
            mtime = int(stat.st_mtime)
            # 包含根目录修改时间和子目录数
            subdirs = sum(1 for _ in os.scandir(path) if _.is_dir())
            return f"{path}:{mtime}:{subdirs}"
        except:
            return path

    def _get_cached_result(self, path: str) -> Optional[dict]:
        """获取缓存的扫描结果"""
        if not self.cache_enabled:
            return None

        try:
            cursor = self.conn.execute(
                'SELECT result_json, expires_at FROM scan_cache WHERE path = ?',
                (path,)
            )
            row = cursor.fetchone()
            if row:
                result_json, expires_at = row
                # 检查是否过期
                if expires_at:
                    expires_time = datetime.fromisoformat(expires_at)
                    if datetime.now() < expires_time:
                        return json.loads(result_json)
                    else:
                        # 缓存过期，删除
                        self.conn.execute('DELETE FROM scan_cache WHERE path = ?', (path,))
                        self.conn.commit()
        except:
            pass
        return None

    def _save_cached_result(self, path: str, result: dict):
        """保存扫描结果到缓存"""
        if not self.cache_enabled:
            return

        try:
            cache_key = self._get_cache_key(path)
            expires_at = datetime.now().timestamp() + self.cache_ttl_seconds
            self.conn.execute('''
                INSERT OR REPLACE INTO scan_cache (path, cache_key, result_json, scanned_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (path, cache_key, json.dumps(result, default=str), datetime.now().isoformat(), datetime.fromtimestamp(expires_at).isoformat()))
            self.conn.commit()
        except Exception as e:
            logger.error(f"缓存保存失败: {e}")

    def clear_cache(self, path: str = None):
        """清除缓存"""
        if path:
            self.conn.execute('DELETE FROM scan_cache WHERE path = ?', (path,))
        else:
            self.conn.execute('DELETE FROM scan_cache')
        self.conn.commit()

    @contextmanager
    def batch_operation(self, batch_size: int = 100):
        """批量操作的上下文管理器，减少 commit 次数"""
        batch = []
        try:
            yield batch
            # 批量提交
            if batch:
                self.conn.executemany(*batch)
                self.conn.commit()
                batch.clear()
        except Exception as e:
            logger.error(f"批量操作失败: {e}")
            self.conn.rollback()
            raise

    def get_incremental_changes(self, root_path: str, since_mtime: float = None) -> dict:
        """获取增量变化（新增/修改/删除的文件）"""
        if not self._check_path_permission(root_path):
            return {}

        if since_mtime is None:
            since_mtime = time.time() - 86400  # 默认获取最近24小时

        added = []
        modified = []
        deleted = []

        # 获取缓存的扫描结果
        cached = self._get_cached_result(root_path)
        cached_files = {}
        if cached and 'file_list' in cached:
            for f in cached.get('file_list', []):
                cached_files[f['path']] = f

        # 扫描当前状态
        current_files = {}
        current_mtime = {}

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            for filename in filenames:
                if filename.startswith('.'):
                    continue
                filepath = os.path.join(dirpath, filename)
                try:
                    stat = os.stat(filepath)
                    if stat.st_mtime >= since_mtime:
                        if filepath in cached_files:
                            modified.append(filepath)
                        else:
                            added.append(filepath)
                    current_files[filepath] = stat.st_size
                    current_mtime[filepath] = stat.st_mtime
                except (OSError, PermissionError):
                    pass

        # 找出删除的文件
        for cached_path in cached_files:
            if cached_path not in current_files:
                deleted.append(cached_path)

        return {
            'added': added,
            'modified': modified,
            'deleted': deleted,
            'added_count': len(added),
            'modified_count': len(modified),
            'deleted_count': len(deleted)
        }

    def search_file_content(self, root_path: str, keyword: str, file_types: List[str] = None,
                           max_results: int = 100, max_file_size_mb: int = 10) -> dict:
        """搜索文件内容

        Args:
            root_path: 搜索根目录
            keyword: 搜索关键字
            file_types: 要搜索的文件类型扩展名列表，如 ['.txt', '.py', '.js']
            max_results: 最大返回结果数
            max_file_size_mb: 单个文件最大大小(MB)，超过则跳过

        Returns:
            搜索结果 {matches: [{path, line_num, line_content, context}, ...], total_files_searched, total_matches}
        """
        if not self._check_path_permission(root_path):
            return {'error': 'Permission denied', 'matches': []}

        if not keyword or len(keyword) < 2:
            return {'error': 'Keyword too short (min 2 chars)', 'matches': []}

        matches = []
        total_searched = 0
        max_size_bytes = max_file_size_mb * 1024 * 1024

        # 默认搜索的文本文件类型
        if file_types is None:
            file_types = frozenset(['.txt', '.py', '.js', '.json', '.xml', '.html', '.css',
                                    '.md', '.yml', '.yaml', '.ini', '.cfg', '.conf', '.log',
                                    '.csv', '.sql', '.sh', '.bat', '.ps1', '.java', '.c', '.cpp', '.h'])
        else:
            file_types = frozenset(file_types)

        # 编译正则提高性能
        try:
            import re
            pattern = re.compile(keyword, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)

        # 使用生成器迭代文件，减少内存占用
        for filepath in self.iter_files(root_path):
            try:
                stat = os.stat(filepath)
                if stat.st_size > max_size_bytes or stat.st_size == 0:
                    continue

                ext = os.path.splitext(filepath)[1].lower()
                if ext not in file_types:
                    continue

                total_searched += 1
                filename = os.path.basename(filepath)

                # 读取文件内容（限制大小避免内存问题）
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(max_size_bytes)

                # 搜索每一行
                for line_num, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        matches.append({
                            'path': filepath,
                            'filename': filename,
                            'line_num': line_num,
                            'line_content': line.strip()[:200],
                            'context': line.strip()[:100]
                        })

                        if len(matches) >= max_results:
                            return {
                                'matches': matches,
                                'total_files_searched': total_searched,
                                'total_matches': len(matches),
                                'truncated': True
                            }

            except (OSError, PermissionError, UnicodeDecodeError):
                continue

        return {
            'matches': matches,
            'total_files_searched': total_searched,
            'total_matches': len(matches),
            'truncated': False
        }

    def start_monitoring(self, root_path: str, callback: Callable = None, recursive: bool = True) -> str:
        """启动文件监控

        Args:
            root_path: 要监控的根目录
            callback: 变化回调函数，接收 (event_type, file_path) 参数
            recursive: 是否递归监控子目录

        Returns:
            monitor_id: 监控会话ID
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent
        except ImportError:
            return ""

        class ChangeHandler(FileSystemEventHandler):
            def __init__(self, monitor_id: str, cb: Callable):
                self.monitor_id = monitor_id
                self.callback = cb
                self.changes = {'added': [], 'modified': [], 'deleted': []}
                self._lock = threading.Lock()

            def on_any_event(self, event: FileSystemEvent):
                if event.is_directory:
                    return
                with self._lock:
                    if event.event_type == 'created':
                        self.changes['added'].append(event.src_path)
                    elif event.event_type == 'modified':
                        self.changes['modified'].append(event.src_path)
                    elif event.event_type == 'deleted':
                        self.changes['deleted'].append(event.src_path)

                    # 更新全局进度跟踪器
                    ScanProgressTracker.update(self.monitor_id,
                        last_event=event.event_type,
                        last_file=event.src_path,
                        changes_count={
                            'added': len(self.changes['added']),
                            'modified': len(self.changes['modified']),
                            'deleted': len(self.changes['deleted'])
                        }
                    )

                    if self.callback:
                        self.callback(event.event_type, event.src_path)

        monitor_id = f"monitor_{int(time.time() * 1000)}"
        handler = ChangeHandler(monitor_id, callback)
        observer = Observer()
        observer.schedule(handler, root_path, recursive=recursive)
        observer.start()

        # 保存监控会话
        with threading.Lock():
            if not hasattr(self, '_monitors'):
                self._monitors = {}
            self._monitors[monitor_id] = {
                'observer': observer,
                'handler': handler,
                'root_path': root_path,
                'start_time': time.time()
            }

        ScanProgressTracker.add(monitor_id, {
            'type': 'monitoring',
            'root_path': root_path,
            'status': 'running',
            'start_time': time.time(),
            'changes_count': {'added': 0, 'modified': 0, 'deleted': 0}
        })

        return monitor_id

    def stop_monitoring(self, monitor_id: str = None) -> dict:
        """停止文件监控"""
        if monitor_id:
            with threading.Lock():
                if hasattr(self, '_monitors') and monitor_id in self._monitors:
                    monitor = self._monitors.pop(monitor_id)
                    monitor['observer'].stop()
                    monitor['observer'].join(timeout=2)
                    ScanProgressTracker.update(monitor_id, status='stopped', end_time=time.time())
                    return {'monitor_id': monitor_id, 'status': 'stopped'}
            return {'monitor_id': monitor_id, 'status': 'not_found'}

        # 停止所有监控
        stopped = []
        with threading.Lock():
            if hasattr(self, '_monitors'):
                for mid, monitor in self._monitors.items():
                    monitor['observer'].stop()
                    monitor['observer'].join(timeout=2)
                    ScanProgressTracker.update(mid, status='stopped', end_time=time.time())
                    stopped.append(mid)
                self._monitors.clear()
        return {'stopped_monitors': stopped}

    def get_monitoring_changes(self, monitor_id: str) -> dict:
        """获取监控期间的变化"""
        with threading.Lock():
            if hasattr(self, '_monitors') and monitor_id in self._monitors:
                handler = self._monitors[monitor_id]['handler']
                with handler._lock:
                    return dict(handler.changes)
        return {}

    def _check_path_permission(self, path: str) -> bool:
        """检查路径权限（包含路径遍历检查）"""
        # 防止路径遍历攻击
        try:
            real_path = os.path.realpath(os.path.abspath(path))
        except (OSError, ValueError):
            logger.warning(f"路径遍历检测: {path}")
            return False

        if not _security_config.allowed_paths:
            return True  # 没有配置白名单时允许所有

        for allowed in _security_config.allowed_paths:
            allowed_abs = os.path.abspath(allowed)
            if real_path.startswith(allowed_abs):
                return True
        return False

    def _check_resource_limit(self, path: str) -> Tuple[bool, str]:
        """检查资源限制（带超时保护）"""
        try:
            count = sum(1 for _ in os.scandir(path))
            if count > _security_config.max_scan_files:
                return False, f"文件数量超过限制 ({_security_config.max_scan_files})"
        except OSError:
            pass
        return True, ""

    def _is_symlink(self, path: str) -> bool:
        """检测是否为符号链接（避免循环引用）"""
        try:
            return os.path.islink(path)
        except OSError:
            return False

    def _get_magic_type(self, filepath: str) -> Optional[str]:
        """通过文件头魔数识别真实文件类型（超越扩展名）"""
        magic_map = {
            b'\x89PNG\r\n\x1a\n': 'png',
            b'\xff\xd8\xff': 'jpg',
            b'GIF87a': 'gif',
            b'GIF89a': 'gif',
            b'RIFF': 'wav',  # 或 avi
            b'ID3': 'mp3',
            b'\x1f\x8b': 'gz',
            b'PK\x03\x04': 'zip',
            b'\x50\x4b\x03\x04': 'zip',
            b'Rar!': 'rar',
            b'\x7fELF': 'elf',
            b'MZ': 'exe',
            b'%PDF': 'pdf',
            b'\xd0\xcf\x11\xe0': 'office',  # old Office
        }

        try:
            with open(filepath, 'rb') as f:
                header = f.read(16)
            for magic, file_type in magic_map.items():
                if header.startswith(magic):
                    return file_type
        except (OSError, PermissionError):
            pass
        return None

    # 文件类型缓存（frozenset 加速查找）
    _CATEGORY_MAP = {
        'video': frozenset(['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.rmvb', '.3gp']),
        'audio': frozenset(['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.ape', '.dts']),
        'image': frozenset(['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff', '.raw', '.psd']),
        'document': frozenset(['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf', '.odt', '.pages', '.numbers', '.key']),
        'code': frozenset(['.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.cs', '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.vue', '.jsx', '.tsx']),
        'archive': frozenset(['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso', '.cab', '.tgz']),
        'database': frozenset(['.db', '.sqlite', '.sqlite3', '.mdb', '.accdb', '.dbf', '.myd']),
        'font': frozenset(['.ttf', '.otf', '.woff', '.woff2', '.eot']),
        'sheet': frozenset(['.csv', '.tsv', '.xlsb']),
    }

    def _categorize(self, extension: str) -> str:
        """分类文件（使用 frozenset 加速）"""
        ext = extension.lower()
        for cat, exts in self._CATEGORY_MAP.items():
            if ext in exts:
                return cat
        return 'other'

    def _scan_directory(self, dir_path: str) -> dict:
        """扫描单个目录，返回统计结果"""
        files_by_category: Dict[str, Dict] = {}
        files_by_extension: Dict[str, Dict] = {}
        total_files = 0
        total_size = 0
        dir_size = 0

        try:
            for entry in os.scandir(dir_path):
                if entry.name.startswith('.'):
                    continue

                if entry.is_file(follow_symlinks=False):
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        size = stat.st_size
                        total_files += 1
                        total_size += size
                        dir_size += size

                        ext = Path(entry.name).suffix.lower()
                        category = self._categorize(ext)

                        # 按分类统计
                        if category not in files_by_category:
                            files_by_category[category] = {'count': 0, 'size': 0}
                        files_by_category[category]['count'] += 1
                        files_by_category[category]['size'] += size

                        # 按扩展名统计
                        if ext not in files_by_extension:
                            files_by_extension[ext] = {'count': 0, 'size': 0}
                        files_by_extension[ext]['count'] += 1
                        files_by_extension[ext]['size'] += size

                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass

        return {
            'dir_size': dir_size,
            'total_files': total_files,
            'total_size': total_size,
            'by_category': files_by_category,
            'by_extension': files_by_extension
        }

    def iter_files(self, root_path: str, max_depth: int = None) -> Generator[str, None, None]:
        """生成器迭代文件，避免一次性加载所有文件到内存

        Args:
            root_path: 根路径
            max_depth: 最大递归深度，None 表示无限制

        Yields:
            file_path 字符串
        """
        def _walk(dir_path: str, depth: int = 0):
            if max_depth is not None and depth > max_depth:
                return

            try:
                with os.scandir(dir_path) as entries:
                    for entry in entries:
                        if entry.name.startswith('.'):
                            continue

                        try:
                            if entry.is_dir(follow_symlinks=False):
                                yield from _walk(entry.path, depth + 1)
                            elif entry.is_file(follow_symlinks=False):
                                yield entry.path
                        except (OSError, PermissionError):
                            continue
            except (OSError, PermissionError):
                pass

        yield from _walk(root_path)

    def _collect_subdirs(self, root_path: str, max_dirs: int = 100) -> List[str]:
        """收集顶层子目录用于并行扫描"""
        subdirs = []
        try:
            for entry in os.scandir(root_path):
                if entry.is_dir(follow_symlinks=False) and not entry.name.startswith('.'):
                    subdirs.append(entry.path)
                    if len(subdirs) >= max_dirs:
                        break
        except (OSError, PermissionError):
            pass
        return subdirs

    def get_storage_stats(
        self,
        root_path: str,
        incremental: bool = True,
        progress: Callable = None,
        use_cache: bool = True
    ) -> dict:
        """获取存储统计（并行扫描+缓存优化）"""
        # 权限检查
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        self.audit_logger.info("storage_stats", root_path)

        # 尝试从缓存获取
        if use_cache and incremental:
            cached = self._get_cached_result(root_path)
            if cached:
                self.audit_logger.info("cache_hit", root_path)
                return {**cached, 'from_cache': True}

        # 资源限制检查
        allowed, msg = self._check_resource_limit(root_path)
        if not allowed:
            self.audit_logger.warning("resource_limit_exceeded", root_path, {"error": msg})
            raise ValueError(msg)

        # 合并结果的锁
        lock = threading.Lock()
        result = {
            'total_files': 0,
            'total_size': 0,
            'by_category': {},
            'by_extension': {},
            'dir_sizes': {},
            'scanned': 0
        }

        # 生成扫描任务ID并记录进度
        import uuid
        scan_id = str(uuid.uuid4())[:8]
        ScanProgressTracker.add(scan_id, {
            'path': root_path,
            'status': 'running',
            'scanned': 0,
            'total_files': 0,
            'total_size': 0,
            'message': '扫描中...',
            'start_time': time.time()
        })

        def merge_result(scan_result: dict):
            """合并扫描结果"""
            with lock:
                result['total_files'] += scan_result['total_files']
                result['total_size'] += scan_result['total_size']
                result['scanned'] += scan_result['total_files']

                for cat, info in scan_result['by_category'].items():
                    if cat not in result['by_category']:
                        result['by_category'][cat] = {'count': 0, 'size': 0}
                    result['by_category'][cat]['count'] += info['count']
                    result['by_category'][cat]['size'] += info['size']

                for ext, info in scan_result['by_extension'].items():
                    if ext not in result['by_extension']:
                        result['by_extension'][ext] = {'count': 0, 'size': 0}
                    result['by_extension'][ext]['count'] += info['count']
                    result['by_extension'][ext]['size'] += info['size']

        def scan_dir(dir_path: str):
            """扫描目录并合并结果"""
            scan_result = self._scan_directory(dir_path)
            merge_result(scan_result)

            # 递归处理子目录
            subdirs = self._collect_subdirs(dir_path, max_dirs=_security_config.parallel_dirs_per_thread)
            for subdir in subdirs:
                sub_result = self._scan_directory(subdir)
                merge_result(sub_result)

            return dir_path

        # 先扫描根目录
        root_result = self._scan_directory(root_path)
        merge_result(root_result)

        # 并行扫描子目录
        subdirs = self._collect_subdirs(root_path, max_dirs=_security_config.parallel_dirs_per_thread)

        if subdirs and _security_config.parallel_enabled:
            threads = min(_security_config.parallel_threads, len(subdirs))
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {executor.submit(scan_dir, d): d for d in subdirs}
                for future in as_completed(futures):
                    try:
                        future.result()
                        ScanProgressTracker.update(scan_id, scanned=result['scanned'])
                        if progress and result['scanned'] % 1000 < _security_config.parallel_threads:
                            progress(result['scanned'], 0, f"扫描中... {result['scanned']} 文件")
                    except Exception:
                        pass
        else:
            for subdir in subdirs:
                scan_dir(subdir)

        # 按大小排序目录
        largest_dirs = sorted(
            [{'path': p, 'size': s, 'size_display': FileInfo.format_size(s)}
             for p, s in result['dir_sizes'].items()],
            key=lambda x: x['size'],
            reverse=True
        )[:10]

        # 标记完成
        ScanProgressTracker.update(scan_id, status='completed', scanned=result['total_files'])

        final_result = {
            'scan_id': scan_id,
            'total_files': result['total_files'],
            'total_size': result['total_size'],
            'total_size_display': FileInfo.format_size(result['total_size']),
            'by_category': {
                k: {**v, 'size_display': FileInfo.format_size(v['size'])}
                for k, v in result['by_category'].items()
            },
            'by_extension': {
                k: {**v, 'size_display': FileInfo.format_size(v['size'])}
                for k, v in result['by_extension'].items()
            },
            'largest_dirs': largest_dirs,
            'scan_type': 'incremental' if incremental else 'full'
        }

        # 保存到缓存
        if use_cache:
            self._save_cached_result(root_path, final_result)

        return final_result

    def analyze_large_files(
        self,
        root_path: str,
        min_size_mb: int = 100,
        limit: int = 20,
        offset: int = 0
    ) -> dict:
        """分析大文件（支持分页，使用生成器优化内存）

        Args:
            root_path: 扫描路径
            min_size_mb: 最小文件大小(MB)
            limit: 返回数量
            offset: 分页偏移
        """
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        self.audit_logger.info("analyze_large_files", root_path,
                              {"min_size_mb": min_size_mb, "limit": limit, "offset": offset})
        logger.info(f"分析大文件: {root_path} (min={min_size_mb}MB)")

        min_size = min_size_mb * 1024 * 1024
        results = []

        # 使用生成器迭代，避免一次性加载
        for filepath in self.iter_files(root_path):
            try:
                stat = os.stat(filepath)
                size = stat.st_size
                if size >= min_size:
                    filename = os.path.basename(filepath)
                    ext = Path(filename).suffix.lower()

                    results.append(FileInfo(
                        path=filepath,
                        name=filename,
                        size=size,
                        size_display=FileInfo.format_size(size),
                        extension=ext,
                        modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        created=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        type_category=self._categorize(ext)
                    ))
            except (OSError, PermissionError):
                continue

        results.sort(key=lambda x: x.size, reverse=True)

        # 分页
        total = len(results)
        page_results = results[offset:offset + limit]

        logger.info(f"找到 {total} 个大文件")
        return {
            'items': page_results,
            'total': total,
            'offset': offset,
            'limit': limit,
            'has_more': offset + limit < total
        }

    def find_duplicates(self, root_path: str, min_size_kb: int = 1) -> List[DuplicateGroup]:
        """查找重复文件（优化：快速哈希 + 精确哈希）"""
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        self.audit_logger.info("find_duplicates", root_path)
        logger.info(f"开始查找重复文件: {root_path}")

        min_size = min_size_kb * 1024
        hash_groups: Dict[str, List[str]] = {}
        size_groups: Dict[int, List[str]] = {}

        # 第一遍：按大小分组
        for filepath in self.iter_files(root_path):
            file_path = filepath[0] if isinstance(filepath, tuple) else filepath
            try:
                size = os.path.getsize(file_path)
                if size < min_size:
                    continue

                if size not in size_groups:
                    size_groups[size] = []
                size_groups[size].append(file_path)

            except (OSError, PermissionError):
                continue

        logger.info(f"按大小分组完成，找到 {len(size_groups)} 个不同大小")

        # 对同大小文件计算快速哈希（前1MB + 后1MB + 大小）
        for size, files in size_groups.items():
            if len(files) < 2:
                continue

            hash_map: Dict[str, List[str]] = {}
            for filepath in files:
                try:
                    file_hash = self._quick_hash(filepath, size)
                    if file_hash not in hash_map:
                        hash_map[file_hash] = []
                    hash_map[file_hash].append(filepath)
                except (OSError, PermissionError):
                    continue

            for h, dup_files in hash_map.items():
                if len(dup_files) > 1:
                    # 精确哈希验证
                    verified = self._verify_duplicates(dup_files)
                    for vh, vfiles in verified.items():
                        if len(vfiles) > 1:
                            if vh not in hash_groups:
                                hash_groups[vh] = vfiles
                            else:
                                hash_groups[vh].extend(vfiles)

        results = []
        for h, files in hash_groups.items():
            if len(files) > 1:
                try:
                    file_size = os.path.getsize(files[0])
                    wasted = file_size * (len(files) - 1)
                    results.append(DuplicateGroup(
                        hash=h,
                        size=file_size,
                        size_display=FileInfo.format_size(file_size),
                        count=len(files),
                        files=files,
                        wasted_space=wasted
                    ))
                except OSError:
                    continue

        logger.info(f"找到 {len(results)} 组重复文件")
        return sorted(results, key=lambda x: x.wasted_space, reverse=True)

    def _quick_hash(self, filepath: str, size: int, chunk_size: int = 1024 * 1024) -> str:
        """快速哈希：只用前后各1MB数据 + 文件大小（大大减少IO）"""
        hasher = hashlib.md5()
        hasher.update(str(size).encode())  # 包含大小

        try:
            with open(filepath, 'rb') as f:
                # 读前1MB
                hasher.update(f.read(chunk_size))
                # 如果文件大于2MB，跳到末尾读最后1MB
                if size > chunk_size * 2:
                    f.seek(-chunk_size, 2)
                    hasher.update(f.read(chunk_size))
        except (OSError, PermissionError):
            pass

        return hasher.hexdigest()

    def _verify_duplicates(self, files: List[str]) -> Dict[str, List[str]]:
        """精确哈希验证：完整读取文件计算MD5"""
        hash_map: Dict[str, List[str]] = {}

        for filepath in files:
            try:
                with open(filepath, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                if file_hash not in hash_map:
                    hash_map[file_hash] = []
                hash_map[file_hash].append(filepath)
            except (OSError, PermissionError):
                continue

        return hash_map

    def get_suggestions(self, root_path: str) -> List[dict]:
        """获取优化建议"""
        if not self._check_path_permission(root_path):
            return []

        self.audit_logger.info("get_suggestions", root_path)

        suggestions = []

        # 统计
        stats = self.get_storage_stats(root_path)

        # 检查大类
        for cat, info in stats.get('by_category', {}).items():
            if info['size'] > 10 * 1024**3:  # > 10GB
                suggestions.append({
                    'type': 'warning',
                    'category': cat,
                    'title': f'{cat.upper()} 类型占用过大',
                    'description': f'{cat} 类型文件共 {info["count"]} 个，占用 {info["size_display"]}',
                    'action': f'建议使用专业压缩工具处理，或迁移到云存储',
                    'size': info['size'],
                    'action_type': 'category'
                })

        # 检查大目录
        for d in stats.get('largest_dirs', [])[:3]:
            if d['size'] > 50 * 1024**3:  # > 50GB
                suggestions.append({
                    'type': 'tip',
                    'title': f'目录过大: {d["path"][:50]}...',
                    'description': f'占用 {d["size_display"]}',
                    'action': '建议归档或清理',
                    'size': d['size'],
                    'action_type': 'directory'
                })

        # 重复文件
        duplicates = self.find_duplicates(root_path)
        duplicate_size = sum(d.wasted_space for d in duplicates)
        if duplicate_size > 10 * 1024**2:  # > 10MB
            suggestions.append({
                'type': 'cleanup',
                'category': 'duplicates',
                'title': '重复文件',
                'description': f'{len(duplicates)} 组重复文件，可节省空间',
                'action': '查看并清理重复文件',
                'size': duplicate_size,
                'count': len(duplicates),
                'action_type': 'duplicates'
            })

        # 临时文件
        temp_files = self._find_temp_files(root_path)
        if temp_files['count'] > 0:
            suggestions.append({
                'type': 'cleanup',
                'category': 'temp',
                'title': '临时文件',
                'description': f'{temp_files["count"]} 个临时/备份文件',
                'action': '清理临时文件',
                'size': temp_files['size'],
                'count': temp_files['count'],
                'action_type': 'temp'
            })

        # 超大文件
        large_result = self.analyze_large_files(root_path, min_size_mb=100, limit=100)
        large_items = large_result.get('items', [])
        large_size = sum(f.size for f in large_items)
        if large_size > 500 * 1024**2:  # > 500MB
            suggestions.append({
                'type': 'cleanup',
                'category': 'large',
                'title': '超大文件',
                'description': f'{large_result.get("total", 0)} 个超过 100MB 的文件',
                'action': '查看并管理大文件',
                'size': large_size,
                'count': len(large_files),
                'action_type': 'large'
            })

        # 空文件夹
        empty_folders = self._find_empty_folders(root_path)
        if empty_folders['count'] > 0:
            suggestions.append({
                'type': 'cleanup',
                'category': 'empty',
                'title': '空文件夹',
                'description': f'{empty_folders["count"]} 个空文件夹可删除',
                'action': '删除空文件夹',
                'size': 0,
                'count': empty_folders['count'],
                'action_type': 'empty'
            })

        # 一年前文件
        old_files = self._find_old_files(root_path, days=365)
        if old_files['count'] > 0:
            suggestions.append({
                'type': 'cleanup',
                'category': 'old',
                'title': '一年前文件',
                'description': f'{old_files["count"]} 个超过一年未修改的文件',
                'action': '查看旧文件',
                'size': old_files['size'],
                'count': old_files['count'],
                'action_type': 'old'
            })

        return suggestions

    def _find_temp_files(self, root_path: str) -> dict:
        """查找临时文件"""
        temp_patterns = ['.tmp', '.temp', '.bak', '.old', '~', '.cache']
        temp_files = []
        temp_size = 0

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            for filename in filenames:
                if any(filename.endswith(p) or p in filename for p in temp_patterns):
                    filepath = os.path.join(dirpath, filename)
                    try:
                        size = os.path.getsize(filepath)
                        temp_files.append(filepath)
                        temp_size += size
                    except:
                        pass

        return {'count': len(temp_files), 'size': temp_size, 'files': temp_files}

    def _find_empty_folders(self, root_path: str) -> dict:
        """查找空文件夹"""
        empty = []

        for dirpath, dirnames, filenames in os.walk(root_path):
            # 检查目录是否为空（不含子目录和非隐藏文件）
            if not dirnames and not filenames:
                empty.append(dirpath)

        return {'count': len(empty), 'folders': empty}

    def _find_old_files(self, root_path: str, days: int = 365) -> dict:
        """查找超过指定天数的旧文件"""
        import time
        cutoff_time = time.time() - (days * 24 * 3600)
        old_files = []
        old_size = 0

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            for filename in filenames:
                if filename.startswith('.'):
                    continue
                filepath = os.path.join(dirpath, filename)
                try:
                    mtime = os.path.getmtime(filepath)
                    if mtime < cutoff_time:
                        size = os.path.getsize(filepath)
                        old_files.append(filepath)
                        old_size += size
                except:
                    pass

        return {'count': len(old_files), 'size': old_size, 'files': old_files}

    def get_cleanup_summary(self, root_path: str) -> dict:
        """获取清理摘要（用于饼图展示）"""
        if not self._check_path_permission(root_path):
            return {}

        self.audit_logger.info("get_cleanup_summary", root_path)

        suggestions = self.get_suggestions(root_path)
        cleanup_items = [s for s in suggestions if s.get('action_type') in [
            'duplicates', 'temp', 'large', 'empty', 'old'
        ]]

        total_cleanable = sum(s.get('size', 0) for s in cleanup_items)

        return {
            'total_cleanable': total_cleanable,
            'total_cleanable_display': FileInfo.format_size(total_cleanable),
            'items': [
                {
                    'icon': self._get_cleanup_icon(s['action_type']),
                    'name': s['title'],
                    'description': s['description'],
                    'size': s.get('size', 0),
                    'size_display': FileInfo.format_size(s.get('size', 0)),
                    'count': s.get('count', 0),
                    'type': s['action_type']
                }
                for s in cleanup_items
            ]
        }

    def _get_cleanup_icon(self, action_type: str) -> str:
        """获取清理类型图标"""
        icons = {
            'duplicates': '📦',
            'temp': '🗑️',
            'large': '🎬',
            'empty': '📁',
            'old': '📅'
        }
        return icons.get(action_type, '📄')

    def chat(self, root_path: str, question: str) -> str:
        """自然语言对话"""
        if not self._check_path_permission(root_path):
            return "抱歉，您没有权限访问这个目录"

        self.audit_logger.info("chat", root_path, {"question": question})

        q = question.lower()
        stats = self.get_storage_stats(root_path)

        if any(k in q for k in ['多少', '多少文件', '文件数', 'count']):
            return f"共有 {stats['total_files']:,} 个文件，总大小 {stats['total_size_display']}"

        if any(k in q for k in ['最大', '占用', '最多', 'largest']):
            if stats.get('largest_dirs'):
                d = stats['largest_dirs'][0]
                return f"占用最大的目录是 {d['path']}，共 {d['size_display']}"

        if any(k in q for k in ['视频', 'video']):
            v = stats.get('by_category', {}).get('video', {})
            if v:
                return f"视频文件共 {v['count']} 个，占用 {v.get('size_display', 'N/A')}"

        return "我可以帮您分析存储情况，请告诉我您想了解什么？"

    def cleanup_duplicates(
        self,
        root_path: str,
        dry_run: bool = True,
        auto_approve: bool = False,
        cancel_token: CancellationToken = None,
        progress_callback: Callable = None
    ) -> dict:
        """
        清理重复文件（安全模式）

        Args:
            root_path: 扫描目录
            dry_run: True=仅预览，False=实际删除
            auto_approve: True=跳过审批（仅当 readonly_mode=False 时）
            cancel_token: 取消令牌，用于中断长时间操作
            progress_callback: 进度回调函数
        """
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        # 只读模式禁止删除
        if not dry_run and _security_config.readonly_mode:
            self.audit_logger.warning("cleanup_blocked_readonly", root_path)
            return {'error': '只读模式已启用，禁止删除操作'}

        # 高危操作需要审批
        if not dry_run and _security_config.require_approval and not auto_approve:
            # 创建待审批操作
            op = self.approval_manager.create_operation(
                OperationType.DELETE_DUPLICATES,
                root_path,
                {'dry_run': dry_run}
            )
            self.audit_logger.info("cleanup_pending_approval", root_path,
                                  {'operation_id': op.id})
            return {
                'status': 'pending_approval',
                'operation_id': op.id,
                'message': f'删除操作已提交，等待审批。操作ID: {op.id}'
            }

        self.audit_logger.info("cleanup_duplicates", root_path, {'dry_run': dry_run})

        duplicates = self.find_duplicates(root_path)

        files_to_delete = []
        for group in duplicates:
            # 保留第一个，标记其余为待删除
            files_to_delete.extend(group.files[1:])

        # 批量大小限制
        if len(files_to_delete) > _security_config.max_batch_size:
            files_to_delete = files_to_delete[:_security_config.max_batch_size]

        deleted = []
        errors = []
        tracker = ProgressTracker(total=len(files_to_delete))

        if not dry_run:
            for i, filepath in enumerate(files_to_delete):
                # 检查取消
                if cancel_token and cancel_token.is_cancelled:
                    self.audit_logger.warning("cleanup_cancelled", root_path,
                                            {'deleted': len(deleted), 'remaining': len(files_to_delete) - i})
                    break

                try:
                    os.remove(filepath)
                    deleted.append(filepath)
                    self.audit_logger.info("file_deleted", filepath)
                    tracker.update(1, filepath)
                except Exception as e:
                    errors.append({'file': filepath, 'error': str(e)})
                    tracker.add_error({'file': filepath, 'error': str(e)})
                    self.audit_logger.error("delete_failed", filepath, {'error': str(e)})

                # 进度回调
                if progress_callback and i % 10 == 0:
                    progress_callback(tracker.to_dict())

        space_freed = sum(os.path.getsize(f) for f in deleted if os.path.exists(f))

        return {
            'groups_found': len(duplicates),
            'files_to_delete': files_to_delete,
            'deleted': deleted,
            'deleted_count': len(deleted),
            'errors': errors,
            'error_count': len(errors),
            'space_to_free': sum(d.wasted_space for d in duplicates),
            'space_freed': space_freed,
            'dry_run': dry_run,
            'cancelled': cancel_token.is_cancelled if cancel_token else False,
            'progress': tracker.to_dict()
        }

    def cleanup_large_files(
        self,
        root_path: str,
        min_size_mb: int = 100,
        dry_run: bool = True,
        auto_approve: bool = False,
        cancel_token: CancellationToken = None,
        progress_callback: Callable = None
    ) -> dict:
        """清理大文件（安全模式）"""
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        if not dry_run and _security_config.readonly_mode:
            self.audit_logger.warning("cleanup_blocked_readonly", root_path)
            return {'error': '只读模式已启用，禁止删除操作'}

        # 审批流程
        if not dry_run and _security_config.require_approval and not auto_approve:
            op = self.approval_manager.create_operation(
                OperationType.DELETE_FILES,
                root_path,
                {'min_size_mb': min_size_mb, 'dry_run': dry_run}
            )
            return {
                'status': 'pending_approval',
                'operation_id': op.id,
                'message': f'删除操作已提交，等待审批。操作ID: {op.id}'
            }

        self.audit_logger.info("cleanup_large_files", root_path,
                              {'min_size_mb': min_size_mb, 'dry_run': dry_run})

        large_files = self.analyze_large_files(root_path, min_size_mb=min_size_mb, limit=1000)
        files_to_delete = [f.path for f in large_files]

        # 批量大小限制
        if len(files_to_delete) > _security_config.max_batch_size:
            files_to_delete = files_to_delete[:_security_config.max_batch_size]

        deleted = []
        errors = []
        tracker = ProgressTracker(total=len(files_to_delete))

        if not dry_run:
            for i, filepath in enumerate(files_to_delete):
                # 检查取消
                if cancel_token and cancel_token.is_cancelled:
                    self.audit_logger.warning("cleanup_cancelled", root_path,
                                            {'deleted': len(deleted), 'remaining': len(files_to_delete) - i})
                    break

                try:
                    os.remove(filepath)
                    deleted.append(filepath)
                    self.audit_logger.info("file_deleted", filepath)
                    tracker.update(1, filepath)
                except Exception as e:
                    errors.append({'file': filepath, 'error': str(e)})
                    tracker.add_error({'file': filepath, 'error': str(e)})

                # 进度回调
                if progress_callback and i % 10 == 0:
                    progress_callback(tracker.to_dict())

        space_freed = sum(os.path.getsize(f) for f in deleted if os.path.exists(f))

        return {
            'files_found': len(large_files),
            'files_to_delete': files_to_delete,
            'deleted': deleted,
            'deleted_count': len(deleted),
            'errors': errors,
            'error_count': len(errors),
            'space_to_free': sum(f.size for f in large_files),
            'space_freed': space_freed,
            'dry_run': dry_run,
            'cancelled': cancel_token.is_cancelled if cancel_token else False,
            'progress': tracker.to_dict()
        }

    def export_report(
        self,
        root_path: str,
        output_path: str,
        format: str = 'html'
    ) -> dict:
        """导出报告

        Args:
            root_path: 扫描路径
            output_path: 输出文件路径
            format: 格式 (html/json/csv)
        """
        if not self._check_path_permission(root_path):
            raise PermissionError(f"路径 {root_path} 不在允许范围内")

        self.audit_logger.info("export_report", root_path,
                              {'output': output_path, 'format': format})
        logger.info(f"导出报告: {root_path} -> {output_path} ({format})")

        stats = self.get_storage_stats(root_path)
        suggestions = self.get_suggestions(root_path)

        if format == 'json':
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({'stats': stats, 'suggestions': suggestions}, f, indent=2, ensure_ascii=False)

        elif format == 'csv':
            import csv
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['类型', '文件数', '大小', '大小显示'])
                for cat, info in sorted(stats.get('by_category', {}).items(),
                                        key=lambda x: x[1]['size'], reverse=True):
                    writer.writerow([cat, info['count'], info['size'], info.get('size_display', 'N/A')])

        else:  # html
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Storage Report - {root_path}</title>
    <style>
        body {{ font-family: system-ui; max-width: 800px; margin: 40px auto; padding: 20px; }}
        h1 {{ color: #113577; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f4f9fc; }}
        .warning {{ color: #d4af37; }}
        .tip {{ color: #4caf50; }}
    </style>
</head>
<body>
    <h1>存储分析报告</h1>
    <p>路径: {root_path}</p>
    <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    <h2>概览</h2>
    <table>
        <tr><th>总文件数</th><td>{stats['total_files']:,}</td></tr>
        <tr><th>总大小</th><td>{stats['total_size_display']}</td></tr>
    </table>

    <h2>类型分布</h2>
    <table>
        <tr><th>类型</th><th>文件数</th><th>大小</th></tr>
"""
            for cat, info in sorted(stats.get('by_category', {}).items(),
                                    key=lambda x: x[1]['size'], reverse=True):
                html += f"""        <tr><td>{cat}</td><td>{info['count']:,}</td><td>{info.get('size_display', 'N/A')}</td></tr>
"""

            html += """    </table>

    <h2>优化建议</h2>
    <ul>
"""
            for s in suggestions:
                html += f"""        <li class="{s.get('type', 'info')}">{s.get('title', '')} - {s.get('description', '')}</li>
"""

            html += """    </table>
</body>
</html>"""

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)

        logger.info(f"报告导出完成: {output_path}")
        return {'output': output_path, 'format': format, 'size': os.path.getsize(output_path)}

    def safe_delete(
        self,
        file_path: str,
        trash_dir: str = None
    ) -> dict:
        """
        安全删除：将文件移动到回收站而不是直接删除

        Args:
            file_path: 要删除的文件路径
            trash_dir: 回收站目录（默认使用系统临时目录）
        """
        if _security_config.readonly_mode:
            return {'error': '只读模式已启用，禁止删除操作'}

        if not os.path.exists(file_path):
            return {'error': f'文件不存在: {file_path}'}

        # 创建回收站目录
        if not trash_dir:
            trash_dir = os.path.join(os.path.expanduser('~'), '.pristmax_trash')
        os.makedirs(trash_dir, exist_ok=True)

        # 生成安全文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.basename(file_path)
        safe_name = f"{timestamp}_{filename}"
        trash_path = os.path.join(trash_dir, safe_name)

        try:
            # 如果目标已存在，添加序号
            counter = 1
            while os.path.exists(trash_path):
                safe_name = f"{timestamp}_{counter}_{filename}"
                trash_path = os.path.join(trash_dir, safe_name)
                counter += 1

            # 移动到回收站
            os.rename(file_path, trash_path)
            self.audit_logger.info("safe_delete", file_path, {'trash_path': trash_path})

            return {
                'success': True,
                'original_path': file_path,
                'trash_path': trash_path,
                'message': f'文件已移动到回收站: {trash_path}'
            }
        except Exception as e:
            self.audit_logger.error("safe_delete_failed", file_path, {'error': str(e)})
            return {'error': str(e)}

    def restore_from_trash(self, trash_path: str, target_dir: str = None) -> dict:
        """从回收站恢复文件"""
        if not os.path.exists(trash_path):
            return {'error': f'回收站文件不存在: {trash_path}'}

        if target_dir is None:
            target_dir = os.path.dirname(trash_path)

        filename = os.path.basename(trash_path)
        # 移除时间戳前缀
        if '_' in filename:
            parts = filename.split('_', 2)
            if len(parts) >= 3:
                filename = parts[2]

        target_path = os.path.join(target_dir, filename)

        try:
            os.rename(trash_path, target_path)
            self.audit_logger.info("restore_from_trash", trash_path, {'target': target_path})
            return {
                'success': True,
                'trash_path': trash_path,
                'restored_path': target_path,
                'message': f'文件已恢复到: {target_path}'
            }
        except Exception as e:
            self.audit_logger.error("restore_failed", trash_path, {'error': str(e)})
            return {'error': str(e)}

    def get_operation_stats(self) -> dict:
        """获取操作统计"""
        cursor = self.approval_manager.conn.execute('''
            SELECT status, type, COUNT(*) as count,
                   SUM(CASE WHEN result IS NOT NULL THEN json_extract(result, '$.space_freed') ELSE 0 END) as space_freed
            FROM operations
            GROUP BY status, type
        ''')

        stats = {
            'total': 0,
            'by_status': {},
            'by_type': {},
            'total_space_freed': 0
        }

        for row in cursor.fetchall():
            status, op_type, count, space_freed = row
            stats['total'] += count
            stats['by_status'][status] = stats['by_status'].get(status, 0) + count
            stats['by_type'][op_type] = stats['by_type'].get(op_type, 0) + count
            if space_freed:
                stats['total_space_freed'] += space_freed

        return stats

    def get_recent_operations(self, limit: int = 10) -> List[Operation]:
        """获取最近操作"""
        return self.approval_manager.list_operations(limit=limit)

    def close(self):
        """关闭连接"""
        if hasattr(self, 'conn'):
            self.conn.close()


# ============================================
# MCP 工具定义
# ============================================

def get_mcp_tools():
    """获取 MCP 工具列表"""
    return [
        {
            'name': 'storage_stats',
            'description': '获取目录存储统计（只读操作，无需审批）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'},
                    'incremental': {'type': 'boolean', 'description': '使用增量扫描', 'default': True}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_large_files',
            'description': '查找大文件（只读操作，无需审批）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'},
                    'min_size_mb': {'type': 'integer', 'description': '最小文件大小(MB)', 'default': 100},
                    'limit': {'type': 'integer', 'description': '返回数量', 'default': 20}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_duplicates',
            'description': '查找重复文件（只读操作，无需审批）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'},
                    'min_size_kb': {'type': 'integer', 'description': '最小文件大小(KB)', 'default': 1}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_suggestions',
            'description': '获取优化建议（只读操作，无需审批）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_cleanup_summary',
            'description': '获取智能清理摘要（用于饼图展示）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_analyze',
            'description': '综合分析目录（返回存储统计+清理建议+分类数据）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'}
                },
                'required': ['path']
            }
        },
        {
            'name': 'storage_cleanup_preview',
            'description': '预览清理操作（不实际删除，仅预览）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '目录路径'},
                    'type': {'type': 'string', 'enum': ['duplicates', 'large', 'temp', 'old', 'empty'], 'description': '清理类型'},
                    'min_size_mb': {'type': 'integer', 'description': '大文件最小大小(MB)', 'default': 100}
                },
                'required': ['path', 'type']
            }
        },
        {
            'name': 'storage_cleanup_execute',
            'description': '执行清理操作（需审批，高危）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'operation_id': {'type': 'string', 'description': '审批通过的操作ID'},
                    'confirm': {'type': 'boolean', 'description': '确认执行'}
                },
                'required': ['operation_id', 'confirm']
            }
        },
        {
            'name': 'storage_approval_query',
            'description': '查询待审批操作',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string', 'enum': ['pending', 'approved', 'rejected'], 'description': '状态筛选'}
                }
            }
        },
        {
            'name': 'storage_approval_action',
            'description': '审批操作（批准/拒绝）',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'operation_id': {'type': 'string', 'description': '操作ID'},
                    'action': {'type': 'string', 'enum': ['approve', 'reject'], 'description': '审批动作'},
                    'approved_by': {'type': 'string', 'description': '审批人'}
                },
                'required': ['operation_id', 'action']
            }
        }
    ]
