"""
M5 Config Module: Configuration Management

M5 核心模块: 配置管理。

功能:
- YAML/JSON 配置加载
- 环境变量覆盖
- 配置验证
- 默认值管理
- 配置热更新
"""
import os
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime


@dataclass
class StorageConfig:
    """存储配置"""
    default_path: str = "./storage"
    max_file_size_mb: int = 10240  # 10 GB
    supported_formats: List[str] = field(default_factory=lambda: ['.mp4', '.avi', '.mkv', '.mov'])

    # NAS 配置
    nas_enabled: bool = False
    nas_host: str = ""
    nas_share: str = ""
    nas_username: str = ""
    nas_password: str = ""

    # 云存储配置
    cloud_enabled: bool = False
    cloud_endpoint: str = ""
    cloud_bucket: str = ""
    cloud_access_key: str = ""
    cloud_secret_key: str = ""


@dataclass
class StrategyConfig:
    """策略配置"""
    enabled: bool = True
    crf: int = 28
    preset: str = "medium"
    blur_kernel: int = 21
    motion_threshold: int = 25

    # 质量门槛
    min_psnr: float = 30.0
    min_ssim: float = 0.90

    # 资源限制
    max_concurrent: int = 2
    max_memory_mb: int = 2048


@dataclass
class DedupConfig:
    """去重配置"""
    enabled: bool = True
    min_chunk_size: int = 1024
    max_chunk_size: int = 65536

    # 分布式
    distributed_enabled: bool = False
    replication_factor: int = 2
    node_id: str = "node-1"


@dataclass
class MonitoringConfig:
    """监控配置"""
    enabled: bool = True
    port: int = 9090
    metrics_interval: int = 60  # 秒

    # 告警
    alert_enabled: bool = True
    alert_email: str = ""
    alert_threshold_disk: float = 90.0
    alert_threshold_memory: float = 85.0


@dataclass
class AppConfig:
    """应用配置"""
    app_name: str = "Pristmax"
    version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 5001

    # 子配置
    storage: StorageConfig = field(default_factory=StorageConfig)
    strategies: Dict[str, StrategyConfig] = field(default_factory=dict)
    dedup: DedupConfig = field(default_factory=DedupConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)

    # 路径
    config_dir: str = "./config"
    data_dir: str = "./data"
    log_dir: str = "./logs"

    def to_dict(self) -> dict:
        result = asdict(self)
        result['storage'] = asdict(self.storage)
        result['dedup'] = asdict(self.dedup)
        result['monitoring'] = asdict(self.monitoring)
        result['strategies'] = {
            k: asdict(v) for k, v in self.strategies.items()
        }
        return result


class ConfigManager:
    """配置管理器"""

    DEFAULT_CONFIG = {
        'app_name': 'Pristmax',
        'version': '1.0.0',
        'debug': False,
        'host': '0.0.0.0',
        'port': 5001,
    }

    def __init__(self, config_path: str = None):
        self.config_path = config_path or os.environ.get('PRISTMAX_CONFIG', os.environ.get('PRISTINE_CONFIG', './config/app.yaml'))
        self.config: AppConfig = None
        self._load()

    def _load(self):
        """加载配置"""
        path = Path(self.config_path)

        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                if path.suffix in ['.yaml', '.yml']:
                    import yaml
                    data = yaml.safe_load(f) or {}
                else:
                    data = json.load(f) or {}
        else:
            data = {}

        data = self._merge_config(self.DEFAULT_CONFIG, data)
        data = self._apply_env_overrides(data)
        self.config = self._create_config(data)

    def _merge_config(self, default: dict, override: dict) -> dict:
        """合并配置"""
        result = default.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result

    def _apply_env_overrides(self, config: dict) -> dict:
        """应用环境变量覆盖"""
        env_mappings = {
            'PRISTMAX_HOST': ('host', str),
            'PRISTMAX_PORT': ('port', int),
            'PRISTMAX_DEBUG': ('debug', lambda x: x.lower() == 'true'),
        }

        for env_key, mapping in env_mappings.items():
            value = os.environ.get(env_key, os.environ.get(env_key.replace('PRISTMAX_', 'PRISTINE_')))
            if value is None:
                continue

            if isinstance(mapping, tuple) and len(mapping) == 2:
                config[mapping[0]] = mapping[1](value)

        return config

    def _create_config(self, data: dict) -> AppConfig:
        """创建配置对象"""
        storage_data = data.get('storage', {})
        storage = StorageConfig(**storage_data)

        dedup_data = data.get('dedup', {})
        dedup = DedupConfig(**dedup_data)

        monitoring_data = data.get('monitoring', {})
        monitoring = MonitoringConfig(**monitoring_data)

        strategies = {}
        for name, strategy_data in data.get('strategies', {}).items():
            strategies[name] = StrategyConfig(**strategy_data)

        return AppConfig(
            app_name=('Pristmax' if str(data.get('app_name', '')).lower() == 'pristine' else data.get('app_name', 'Pristmax')),
            version=data.get('version', '1.0.0'),
            debug=data.get('debug', False),
            host=data.get('host', '0.0.0.0'),
            port=data.get('port', 5001),
            storage=storage,
            dedup=dedup,
            monitoring=monitoring,
            strategies=strategies
        )

    def get(self) -> AppConfig:
        """获取配置"""
        return self.config

    def save(self, path: str = None):
        """保存配置"""
        path = path or self.config_path
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.config.to_dict()

        with open(path, 'w', encoding='utf-8') as f:
            if path.suffix in ['.yaml', '.yml']:
                import yaml
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def reload(self):
        """重新加载配置"""
        self._load()

    def validate(self) -> List[str]:
        """验证配置"""
        errors = []

        if self.config.port < 1 or self.config.port > 65535:
            errors.append(f"Invalid port: {self.config.port}")

        if not self.config.storage.default_path:
            errors.append("Storage path is required")

        for name, strategy in self.config.strategies.items():
            if strategy.crf < 0 or strategy.crf > 51:
                errors.append(f"Strategy {name}: CRF must be 0-51")

        return errors


_config: Optional[ConfigManager] = None


def get_config() -> AppConfig:
    """获取全局配置"""
    global _config
    if _config is None:
        _config = ConfigManager()
    return _config.config


def init_config(config_path: str = None) -> AppConfig:
    """初始化配置"""
    global _config
    _config = ConfigManager(config_path)
    return _config.config
