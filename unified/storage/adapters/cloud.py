"""
Cloud Adapter

云存储适配器，支持 S3 兼容存储 (AWS S3, 阿里云 OSS, 腾讯云 COS, MinIO 等)
"""
import os
from typing import Iterator, Optional, List, Dict
from pathlib import Path

from storage.base import (
    StorageType, StorageInfo, FileInfo, ScanProgress,
    StorageAdapter
)


class CloudAdapter(StorageAdapter):
    """
    云存储适配器

    支持 S3 兼容的对象存储服务

    Features:
    - 多云服务商支持 (AWS, 阿里云, 腾讯云, MinIO)
    - 列表操作 (ListObjects)
    - 哈希计算 (服务端或本地)
    - 分片上传/下载

    Example:
        # AWS S3
        adapter = CloudAdapter({
            'id': 's3-001',
            'name': 'AWS S3',
            'provider': 'aws',
            'bucket': 'my-bucket',
            'region': 'us-east-1',
            'access_key': 'AKIA...',
            'secret_key': '...'
        })

        # 阿里云 OSS
        adapter = CloudAdapter({
            'id': 'oss-001',
            'name': '阿里云 OSS',
            'provider': 'aliyun',
            'bucket': 'my-bucket',
            'region': 'oss-cn-hangzhou',
            'access_key': '...',
            'secret_key': '...'
        })

        # MinIO 自建
        adapter = CloudAdapter({
            'id': 'minio-001',
            'name': 'MinIO 存储',
            'provider': 'minio',
            'bucket': 'my-bucket',
            'endpoint': 'http://192.168.1.100:9000',
            'access_key': 'minioadmin',
            'secret_key': 'minioadmin'
        })
    """

    # 支持的云服务商
    PROVIDERS = ['aws', 'aliyun', 'tencent', 'minio', 'custom']

    def __init__(self, config: dict):
        super().__init__(config)
        self.provider = config.get('provider', 'aws').lower()
        self.bucket = config.get('bucket', '')
        self.region = config.get('region', 'us-east-1')
        self.access_key = config.get('access_key', '')
        self.secret_key = config.get('secret_key', '')
        self.endpoint = config.get('endpoint')  # MinIO/Custom 使用

        # S3 客户端 (延迟初始化)
        self._client = None
        self._resource = None

    @property
    def storage_type(self) -> StorageType:
        return StorageType.CLOUD

    def connect(self) -> bool:
        """连接到云存储"""
        try:
            self._init_client()
            # 验证连接
            self._client.list_buckets()
            self._is_connected = True
            return True
        except Exception as e:
            print(f"[Cloud] Connection failed: {e}")
            return False

    def _init_client(self):
        """初始化 S3 客户端"""
        if self._client is not None:
            return

        try:
            import boto3
            from botocore.config import Config

            # 配置连接参数
            config = Config(
                retries={'max_attempts': 3},
                connect_timeout=5,
                read_timeout=30,
            )

            if self.provider == 'aws':
                # AWS S3
                self._client = boto3.client(
                    's3',
                    region_name=self.region,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    config=config
                )
                self._resource = boto3.resource(
                    's3',
                    region_name=self.region,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                )

            elif self.provider == 'aliyun':
                # 阿里云 OSS
                import oss2
                auth = oss2.Auth(self.access_key, self.secret_key)
                # 注意: 阿里云 OSS 使用不同的 API
                self._oss_auth = auth
                # 简化处理，实际使用 oss2 SDK

            elif self.provider == 'tencent':
                # 腾讯云 COS
                import qcloud_cos
                self._cos = qcloud_cos.CosService(
                    self.access_key, self.secret_key, self.region
                )

            elif self.provider == 'minio' or self.provider == 'custom':
                # MinIO 或兼容 S3 的自建存储
                endpoint = self.endpoint or 'http://localhost:9000'

                self._client = boto3.client(
                    's3',
                    endpoint_url=endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    config=Config(signature_version='s3v4')
                )
                self._resource = boto3.resource(
                    's3',
                    endpoint_url=endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    config=Config(signature_version='s3v4')
                )

            else:
                raise ValueError(f"Unknown provider: {self.provider}")

        except ImportError as e:
            print(f"[Cloud] Missing dependency: {e}")
            raise
        except Exception as e:
            print(f"[Cloud] Client init failed: {e}")
            raise

    def disconnect(self):
        """断开连接"""
        self._client = None
        self._resource = None
        self._is_connected = False

    def get_info(self) -> StorageInfo:
        """获取云存储信息"""
        if not self._client:
            return StorageInfo(
                name=self._storage_name or f"云存储 ({self.provider})",
                storage_type=StorageType.CLOUD,
                path=f"{self.bucket}",
                status="offline",
            )

        try:
            # 获取 Bucket 信息
            if self.provider == 'aws' or self.provider in ['minio', 'custom']:
                response = self._client.head_bucket(Bucket=self.bucket)
                return StorageInfo(
                    name=self._storage_name or f"{self.provider.upper()} {self.bucket}",
                    storage_type=StorageType.CLOUD,
                    path=self.bucket,
                    status="healthy",
                    metadata={
                        'provider': self.provider,
                        'region': self.region,
                        'bucket': self.bucket,
                    }
                )

        except Exception as e:
            return StorageInfo(
                name=self._storage_name or f"云存储 ({self.provider})",
                storage_type=StorageType.CLOUD,
                path=self.bucket,
                status="error",
                metadata={'error': str(e)}
            )

        return StorageInfo(
            name=self._storage_name or f"云存储 ({self.bucket})",
            storage_type=StorageType.CLOUD,
            path=self.bucket,
            status="unknown",
        )

    def scan(
        self,
        path: str = "/",
        recursive: bool = True,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """扫描云存储 Objects"""
        if not self._client:
            if not self.connect():
                return

        prefix = path.lstrip('/') if path != "/" else ""

        try:
            if self.provider == 'aws' or self.provider in ['minio', 'custom']:
                yield from self._scan_s3(prefix, recursive, progress_callback)
            elif self.provider == 'aliyun':
                yield from self._scan_oss(prefix, recursive, progress_callback)
            elif self.provider == 'tencent':
                yield from self._scan_cos(prefix, recursive, progress_callback)

        except Exception as e:
            print(f"[Cloud] Scan failed: {e}")

    def _scan_s3(
        self,
        prefix: str,
        recursive: bool,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """扫描 S3 存储桶"""
        continuation_token = None

        while True:
            if recursive:
                kwargs = {
                    'Bucket': self.bucket,
                    'Prefix': prefix,
                    'MaxKeys': 1000,
                }
                if continuation_token:
                    kwargs['ContinuationToken'] = continuation_token

                response = self._client.list_objects_v2(**kwargs)
            else:
                kwargs = {
                    'Bucket': self.bucket,
                    'Prefix': prefix,
                    'Delimiter': '/',
                    'MaxKeys': 1000,
                }
                if continuation_token:
                    kwargs['ContinuationToken'] = continuation_token

                response = self._client.list_objects_v2(**kwargs)

            # 处理对象
            if 'Contents' in response:
                for obj in response['Contents']:
                    file_info = FileInfo(
                        path=obj['Key'],
                        relative_path=obj['Key'],
                        size=obj['Size'],
                        modified_time=obj['LastModified'].timestamp() if hasattr(obj['LastModified'], 'timestamp') else 0,
                        storage_type=StorageType.CLOUD,
                        is_directory=False,
                        extension=self._get_file_extension(obj['Key']),
                    )
                    yield file_info

            # 检查是否还有更多
            if not response.get('IsTruncated', False):
                break

            continuation_token = response.get('NextContinuationToken')

    def _scan_oss(
        self,
        prefix: str,
        recursive: bool,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """扫描阿里云 OSS"""
        # 简化实现，实际需要 oss2 库
        try:
            import oss2
            bucket = oss2.Bucket(self._oss_auth, f'oss-{self.region}.aliyuncs.com', self.bucket)

            for obj in oss2.ObjectIteratorV2(bucket, prefix=prefix):
                yield FileInfo(
                    path=obj.key,
                    relative_path=obj.key,
                    size=obj.size,
                    modified_time=obj.last_modified,
                    storage_type=StorageType.CLOUD,
                    is_directory=False,
                    extension=self._get_file_extension(obj.key),
                )
        except Exception as e:
            print(f"[Cloud] OSS scan error: {e}")

    def _scan_cos(
        self,
        prefix: str,
        recursive: bool,
        progress_callback=None
    ) -> Iterator[FileInfo]:
        """扫描腾讯云 COS"""
        # 简化实现
        try:
            import json
            response = self._cos.list_object(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=1000
            )

            if 'Contents' in response:
                for obj in response['Contents']:
                    yield FileInfo(
                        path=obj['Key'],
                        relative_path=obj['Key'],
                        size=int(obj['Size']),
                        modified_time=0,  # COS 响应格式可能不同
                        storage_type=StorageType.CLOUD,
                        is_directory=False,
                        extension=self._get_file_extension(obj['Key']),
                    )
        except Exception as e:
            print(f"[Cloud] COS scan error: {e}")

    def read_file(self, path: str, offset: int = 0, size: Optional[int] = None) -> bytes:
        """读取云存储文件内容"""
        if not self._client:
            self.connect()

        try:
            if self.provider == 'aws' or self.provider in ['minio', 'custom']:
                response = self._client.get_object(Bucket=self.bucket, Key=path)
                body = response['Body'].read()

                if offset > 0 or size is not None:
                    if offset > 0:
                        body = body[offset:]
                    if size is not None:
                        body = body[:size]

                return body

        except Exception as e:
            print(f"[Cloud] Read failed: {e}")
            return b''

    def compute_hash(
        self,
        path: str,
        algorithm: str = "sha256",
        chunk_size: int = 8192
    ) -> str:
        """
        计算云存储文件的 ETag (通常是 MD5)

        注意: 云存储的对象 ETag 就是 MD5
        """
        try:
            if self.provider == 'aws' or self.provider in ['minio', 'custom']:
                response = self._client.head_object(Bucket=self.bucket, Key=path)
                # ETag 可能是 "abc123" 或 "abc123-2" (分片上传)
                etag = response.get('ETag', '').strip('"')
                if '-' not in etag:  # 不是分片上传
                    return etag

            # 分片上传或不支持的情况，计算本地哈希
            data = self.read_file(path)
            import hashlib

            if algorithm == "md5":
                return hashlib.md5(data).hexdigest()
            elif algorithm == "sha1":
                return hashlib.sha1(data).hexdigest()
            else:
                return hashlib.sha256(data).hexdigest()

        except Exception as e:
            print(f"[Cloud] Hash failed: {e}")
            return ""

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """上传文件到云存储"""
        if not self._client:
            self.connect()

        try:
            self._client.upload_file(Bucket=self.bucket, Key=remote_path, Filename=local_path)
            return True
        except Exception as e:
            print(f"[Cloud] Upload failed: {e}")
            return False

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """从云存储下载文件"""
        if not self._client:
            self.connect()

        try:
            self._client.download_file(Bucket=self.bucket, Key=remote_path, Filename=local_path)
            return True
        except Exception as e:
            print(f"[Cloud] Download failed: {e}")
            return False

    def delete_object(self, path: str) -> bool:
        """删除云存储对象"""
        if not self._client:
            self.connect()

        try:
            self._client.delete_object(Bucket=self.bucket, Key=path)
            return True
        except Exception as e:
            print(f"[Cloud] Delete failed: {e}")
            return False
