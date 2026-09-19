# -*- coding: utf-8 -*-
"""
Configuration Management

Loads configuration from YAML files and environment variables.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


class Config:
    """
    Configuration manager for the semantic reduction system.

    Supports:
    - YAML configuration files
    - Environment variable overrides
    - Default values
    """

    DEFAULT_CONFIG = {
        'system': {
            'name': 'SemanticReduction',
            'version': '1.0.0',
            'debug': False,
        },
        'processing': {
            'batch_size': 100,
            'max_workers': 4,
            'timeout_seconds': 300,
        },
        'video': {
            'frame_skip': 1,
            'motion_threshold': 0.05,
            'min_brightness': 0.1,
            'min_sharpness': 0.3,
            'preserve_with_faces': True,
            'preserve_with_people': True,
            'preserve_with_vehicles': True,
            'low_value_downsample_ratio': 0.1,
        },
        'log': {
            'default_sampling_rate': 0.1,
            'preserve_error': True,
            'preserve_warn': True,
            'discard_trace': True,
        },
        'storage': {
            'type': 'filesystem',
            'base_path': './data',
            'audit_path': './data/audit',
        },
        'audit': {
            'enabled': True,
            'path': './data/audit',
            'retention_days': 365,
        },
        'roi': {
            'storage_cost_per_tb': 5000,
            'currency': 'CNY',
        }
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to YAML configuration file
        """
        self._config = self.DEFAULT_CONFIG.copy()

        if config_path and os.path.exists(config_path):
            self.load(config_path)

        # Override with environment variables
        self._load_env_overrides()

    def load(self, config_path: str) -> None:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to YAML file
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = yaml.safe_load(f)

        if user_config:
            self._merge_config(self._config, user_config)

    def _merge_config(self, base: Dict, update: Dict) -> None:
        """Recursively merge update into base"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def _load_env_overrides(self) -> None:
        """Load configuration overrides from environment variables"""
        # System
        if os.getenv('SR_DEBUG'):
            self._config['system']['debug'] = os.getenv('SR_DEBUG').lower() == 'true'

        # Storage paths
        if os.getenv('SR_BASE_PATH'):
            self._config['storage']['base_path'] = os.getenv('SR_BASE_PATH')
        if os.getenv('SR_AUDIT_PATH'):
            self._config['audit']['path'] = os.getenv('SR_AUDIT_PATH')

        # ROI
        if os.getenv('SR_STORAGE_COST'):
            self._config['roi']['storage_cost_per_tb'] = float(os.getenv('SR_STORAGE_COST'))

        # Processing
        if os.getenv('SR_MAX_WORKERS'):
            self._config['processing']['max_workers'] = int(os.getenv('SR_MAX_WORKERS'))

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.

        Args:
            key: Dot-notation key (e.g., 'video.motion_threshold')
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value by dot-notation key.

        Args:
            key: Dot-notation key
            value: Value to set
        """
        keys = key.split('.')
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def to_dict(self) -> Dict:
        """Return configuration as dictionary"""
        return self._config.copy()

    def save(self, config_path: str) -> None:
        """
        Save current configuration to YAML file.

        Args:
            config_path: Path to save file
        """
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)

    @classmethod
    def create_sample(cls, output_path: str) -> 'Config':
        """
        Create a sample configuration file.

        Args:
            output_path: Path to save sample config

        Returns:
            Config instance with sample values
        """
        config = cls()
        config.save(output_path)
        return config


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global config instance"""
    global _config
    if _config is None:
        _config = Config()
    return _config


def init_config(config_path: Optional[str] = None) -> Config:
    """
    Initialize global config instance.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Config instance
    """
    global _config
    _config = Config(config_path)
    return _config
