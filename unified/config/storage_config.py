"""
Storage Configuration

存储配置文件定义和操作
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class MountPoint:
    """挂载点配置"""
    path: str
    enabled: bool = True
    exclude_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'path': self.path,
            'enabled': self.enabled,
            'exclude_paths': self.exclude_paths,
        }


@dataclass
class StorageConfig:
    """存储配置"""
    id: str
    name: str
    type: str  # local_disk, nas, usb, cloud, raid
    enabled: bool = True
    mount_points: List[str] = field(default_factory=list)
    exclude_paths: List[str] = field(default_factory=list)
    exclude_extensions: List[str] = field(default_factory=list)
    min_file_size: int = 0
    # NAS 特有
    host: Optional[str] = None
    share: Optional[str] = None
    protocol: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    # 云存储特有
    provider: Optional[str] = None
    bucket: Optional[str] = None
    region: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    endpoint: Optional[str] = None
    # RAID 特有
    raid_type: Optional[str] = None
    controller: Optional[str] = None
    # 额外配置
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典"""
        result = {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'enabled': self.enabled,
            'mount_points': self.mount_points,
            'exclude_paths': self.exclude_paths,
            'exclude_extensions': self.exclude_extensions,
            'min_file_size': self.min_file_size,
        }

        # NAS 配置
        if self.host:
            result['host'] = self.host
        if self.share:
            result['share'] = self.share
        if self.protocol:
            result['protocol'] = self.protocol
        if self.username:
            result['username'] = self.username
        if self.password:
            result['password'] = self.password

        # 云存储配置
        if self.provider:
            result['provider'] = self.provider
        if self.bucket:
            result['bucket'] = self.bucket
        if self.region:
            result['region'] = self.region
        if self.access_key:
            result['access_key'] = self.access_key
        if self.secret_key:
            result['secret_key'] = self.secret_key
        if self.endpoint:
            result['endpoint'] = self.endpoint

        # RAID 配置
        if self.raid_type:
            result['raid_type'] = self.raid_type
        if self.controller:
            result['controller'] = self.controller

        # 元数据
        if self.metadata:
            result['metadata'] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: dict) -> 'StorageConfig':
        """从字典创建"""
        return cls(
            id=data.get('id', ''),
            name=data.get('name', ''),
            type=data.get('type', 'local_disk'),
            enabled=data.get('enabled', True),
            mount_points=data.get('mount_points', []),
            exclude_paths=data.get('exclude_paths', []),
            exclude_extensions=data.get('exclude_extensions', []),
            min_file_size=data.get('min_file_size', 0),
            host=data.get('host'),
            share=data.get('share'),
            protocol=data.get('protocol'),
            username=data.get('username'),
            password=data.get('password'),
            provider=data.get('provider'),
            bucket=data.get('bucket'),
            region=data.get('region'),
            access_key=data.get('access_key'),
            secret_key=data.get('secret_key'),
            endpoint=data.get('endpoint'),
            raid_type=data.get('raid_type'),
            controller=data.get('controller'),
            metadata=data.get('metadata', {}),
        )


def get_default_config() -> Dict:
    """获取默认配置"""
    return {
        "version": "1.0",
        "storages": [],
        "settings": {
            "scan": {
                "default_recursive": True,
                "min_file_size": 1024,
                "max_concurrent": 4,
                "hash_algorithm": "sha256",
            },
            "dedup": {
                "enabled": True,
                "hash_algorithm": "sha256",
                "min_duplicate_size": 1024,
            },
            "performance": {
                "chunk_size": 8192,
                "buffer_size": 65536,
                "io_mode": "buffered",  # buffered, direct
            }
        }
    }


def get_config_path() -> Path:
    """获取配置文件路径"""
    base_dir = Path(__file__).parent.parent
    return base_dir / "config" / "storages.json"


def load_config() -> Dict:
    """加载配置"""
    config_path = get_config_path()

    if not config_path.exists():
        return get_default_config()

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Config] Failed to load: {e}")
        return get_default_config()


def save_config(config: Dict) -> bool:
    """保存配置"""
    config_path = get_config_path()

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Config] Failed to save: {e}")
        return False


def add_storage(config: Dict, storage: StorageConfig) -> Dict:
    """添加存储配置"""
    if 'storages' not in config:
        config['storages'] = []

    # 检查是否已存在
    for i, s in enumerate(config['storages']):
        if s.get('id') == storage.id:
            config['storages'][i] = storage.to_dict()
            return config

    config['storages'].append(storage.to_dict())
    return config


def remove_storage(config: Dict, storage_id: str) -> Dict:
    """移除存储配置"""
    if 'storages' not in config:
        return config

    config['storages'] = [
        s for s in config['storages']
        if s.get('id') != storage_id
    ]
    return config


def get_storage(config: Dict, storage_id: str) -> Optional[StorageConfig]:
    """获取存储配置"""
    if 'storages' not in config:
        return None

    for s in config['storages']:
        if s.get('id') == storage_id:
            return StorageConfig.from_dict(s)

    return None


def update_settings(config: Dict, settings: Dict) -> Dict:
    """更新设置"""
    if 'settings' not in config:
        config['settings'] = {}

    deep_update(config['settings'], settings)
    return config


def deep_update(base: Dict, update: Dict):
    """深度更新字典"""
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_update(base[key], value)
        else:
            base[key] = value
