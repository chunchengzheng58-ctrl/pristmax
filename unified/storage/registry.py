"""
Storage Registry

存储适配器注册表，用于管理可用存储类型的注册和发现
"""
from typing import Dict, Type, Optional, List
from storage.base import StorageAdapter, StorageType


class StorageRegistry:
    """
    存储适配器注册表

    负责存储适配器的注册、注销和获取

    Example:
        registry = StorageRegistry()

        # 注册适配器
        registry.register(StorageType.LOCAL_DISK, LocalDiskAdapter)

        # 获取适配器类
        adapter_class = registry.get(StorageType.LOCAL_DISK)

        # 创建适配器实例
        adapter = registry.create(StorageType.LOCAL_DISK, config)
    """

    _instance = None

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters = {}
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化注册表 (仅首次)"""
        if not self._initialized:
            self._adapters: Dict[StorageType, Type[StorageAdapter]] = {}
            self._initialized = True
            self._auto_register_defaults()

    def _auto_register_defaults(self):
        """自动注册内置适配器"""
        from storage.adapters import (
            LocalDiskAdapter,
            NASAdapter,
            USBAdapter,
            CloudAdapter,
            RAIDAdapter,
        )

        self.register(StorageType.LOCAL_DISK, LocalDiskAdapter)
        self.register(StorageType.NAS, NASAdapter)
        self.register(StorageType.USB, USBAdapter)
        self.register(StorageType.CLOUD, CloudAdapter)
        self.register(StorageType.RAID, RAIDAdapter)

    def register(self, storage_type: StorageType, adapter_class: Type[StorageAdapter]) -> None:
        """
        注册存储适配器

        Args:
            storage_type: 存储类型
            adapter_class: 适配器类

        Raises:
            ValueError: 如果适配器类不继承自 StorageAdapter
        """
        if not issubclass(adapter_class, StorageAdapter):
            raise ValueError(
                f"Adapter class must inherit from StorageAdapter, "
                f"got {adapter_class.__name__}"
            )

        if storage_type in self._adapters:
            # 替换已存在的适配器
            old_class = self._adapters[storage_type]
            self._adapters[storage_type] = adapter_class
            print(f"[Registry] Replaced {storage_type.value}: {old_class.__name__} -> {adapter_class.__name__}")
        else:
            self._adapters[storage_type] = adapter_class
            print(f"[Registry] Registered: {storage_type.value} -> {adapter_class.__name__}")

    def unregister(self, storage_type: StorageType) -> bool:
        """
        注销存储适配器

        Args:
            storage_type: 存储类型

        Returns:
            bool: 是否成功注销
        """
        if storage_type in self._adapters:
            del self._adapters[storage_type]
            print(f"[Registry] Unregistered: {storage_type.value}")
            return True
        return False

    def get(self, storage_type: StorageType) -> Optional[Type[StorageAdapter]]:
        """
        获取适配器类

        Args:
            storage_type: 存储类型

        Returns:
            适配器类，如果未注册返回 None
        """
        return self._adapters.get(storage_type)

    def create(self, storage_type: StorageType, config: dict) -> Optional[StorageAdapter]:
        """
        创建适配器实例

        Args:
            storage_type: 存储类型
            config: 适配器配置

        Returns:
            适配器实例，如果未注册返回 None
        """
        adapter_class = self.get(storage_type)
        if adapter_class is None:
            return None
        return adapter_class(config)

    def list_registered(self) -> List[StorageType]:
        """
        列出所有已注册的存储类型

        Returns:
            已注册的存储类型列表
        """
        return list(self._adapters.keys())

    def is_registered(self, storage_type: StorageType) -> bool:
        """
        检查存储类型是否已注册

        Args:
            storage_type: 存储类型

        Returns:
            bool: 是否已注册
        """
        return storage_type in self._adapters

    def clear(self) -> None:
        """清空所有注册 (主要用于测试)"""
        self._adapters.clear()

    def __repr__(self) -> str:
        return f"<StorageRegistry registered={[t.value for t in self._adapters.keys()]}>"
