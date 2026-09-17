"""
Storage Module Tests

测试存储抽象层的核心功能
"""
import unittest
import tempfile
import os
from pathlib import Path

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.base import StorageType, StorageInfo, FileInfo, StorageAdapter
from storage.registry import StorageRegistry
from storage.manager import StorageManager
from storage.adapters.local_disk import LocalDiskAdapter


class TestStorageType(unittest.TestCase):
    """测试存储类型枚举"""

    def test_storage_types(self):
        """验证所有存储类型"""
        self.assertEqual(StorageType.LOCAL_DISK.value, "local_disk")
        self.assertEqual(StorageType.NAS.value, "nas")
        self.assertEqual(StorageType.USB.value, "usb")
        self.assertEqual(StorageType.CLOUD.value, "cloud")
        self.assertEqual(StorageType.RAID.value, "raid")

    def test_storage_type_count(self):
        """验证存储类型数量"""
        self.assertEqual(len(StorageType), 5)


class TestStorageInfo(unittest.TestCase):
    """测试存储信息数据类"""

    def test_storage_info_creation(self):
        """创建存储信息"""
        info = StorageInfo(
            name="测试磁盘",
            storage_type=StorageType.LOCAL_DISK,
            path="/dev/sda1",
            total_size=1000000000000,
            used_size=500000000000,
            free_size=500000000000,
            is_mounted=True,
            status="healthy"
        )

        self.assertEqual(info.name, "测试磁盘")
        self.assertEqual(info.storage_type, StorageType.LOCAL_DISK)
        self.assertEqual(info.total_size, 1000000000000)
        self.assertEqual(info.usage_percent, 50.0)

    def test_usage_percent(self):
        """测试使用率计算"""
        info = StorageInfo(
            name="测试",
            storage_type=StorageType.LOCAL_DISK,
            path="/",
            total_size=1000,
            used_size=250,
            free_size=750
        )

        self.assertEqual(info.usage_percent, 25.0)

    def test_to_dict(self):
        """测试转换为字典"""
        info = StorageInfo(
            name="测试",
            storage_type=StorageType.LOCAL_DISK,
            path="/",
            total_size=1000,
            used_size=500,
            free_size=500
        )

        d = info.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d['name'], "测试")
        self.assertEqual(d['type'], "local_disk")
        self.assertEqual(d['usage_percent'], 50.0)


class TestFileInfo(unittest.TestCase):
    """测试文件信息数据类"""

    def test_file_info_creation(self):
        """创建文件信息"""
        file_info = FileInfo(
            path="/home/user/document.txt",
            relative_path="document.txt",
            size=1024,
            modified_time=1234567890.0,
            storage_type=StorageType.LOCAL_DISK,
            extension="txt"
        )

        self.assertEqual(file_info.path, "/home/user/document.txt")
        self.assertEqual(file_info.size, 1024)
        self.assertEqual(file_info.extension, "txt")

    def test_file_extension(self):
        """测试文件扩展名提取"""
        file_info = FileInfo(
            path="/test/file.PDF",
            relative_path="file.PDF",
            size=100,
            modified_time=0,
            extension="pdf"
        )

        # 扩展名存储为小写
        self.assertEqual(file_info.extension, "pdf")


class TestStorageRegistry(unittest.TestCase):
    """测试存储注册表"""

    def setUp(self):
        """每个测试前重置注册表"""
        self.registry = StorageRegistry()
        self.registry.clear()

    def test_register_adapter(self):
        """测试注册适配器"""
        self.registry.register(StorageType.LOCAL_DISK, LocalDiskAdapter)
        self.assertTrue(self.registry.is_registered(StorageType.LOCAL_DISK))

    def test_get_adapter(self):
        """测试获取适配器"""
        self.registry.register(StorageType.LOCAL_DISK, LocalDiskAdapter)
        adapter_class = self.registry.get(StorageType.LOCAL_DISK)
        self.assertEqual(adapter_class, LocalDiskAdapter)

    def test_create_adapter(self):
        """测试创建适配器实例"""
        self.registry.register(StorageType.LOCAL_DISK, LocalDiskAdapter)
        config = {'id': 'test-001', 'name': '测试磁盘'}

        adapter = self.registry.create(StorageType.LOCAL_DISK, config)
        self.assertIsInstance(adapter, LocalDiskAdapter)
        self.assertEqual(adapter.storage_id, 'test-001')

    def test_unregister_adapter(self):
        """测试注销适配器"""
        self.registry.register(StorageType.LOCAL_DISK, LocalDiskAdapter)
        self.assertTrue(self.registry.is_registered(StorageType.LOCAL_DISK))

        self.registry.unregister(StorageType.LOCAL_DISK)
        self.assertFalse(self.registry.is_registered(StorageType.LOCAL_DISK))

    def test_list_registered(self):
        """测试列出已注册适配器"""
        self.registry.register(StorageType.LOCAL_DISK, LocalDiskAdapter)
        self.registry.register(StorageType.NAS, LocalDiskAdapter)

        registered = self.registry.list_registered()
        self.assertEqual(len(registered), 2)
        self.assertIn(StorageType.LOCAL_DISK, registered)
        self.assertIn(StorageType.NAS, registered)


class TestLocalDiskAdapter(unittest.TestCase):
    """测试本地磁盘适配器"""

    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()

        # 创建测试文件
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, 'w') as f:
            f.write("Hello, World!")

        # 创建子目录和文件
        self.sub_dir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(self.sub_dir)
        self.sub_file = os.path.join(self.sub_dir, "sub.txt")
        with open(self.sub_file, 'w') as f:
            f.write("Sub content")

    def tearDown(self):
        """清理测试环境"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_adapter_creation(self):
        """测试适配器创建"""
        config = {
            'id': 'test-local',
            'name': '测试磁盘',
            'mount_points': [self.temp_dir]
        }

        adapter = LocalDiskAdapter(config)
        self.assertEqual(adapter.storage_type, StorageType.LOCAL_DISK)
        self.assertEqual(adapter.storage_id, 'test-local')

    def test_connect(self):
        """测试连接"""
        adapter = LocalDiskAdapter({'id': 'test'})
        result = adapter.connect()
        self.assertTrue(result)
        self.assertTrue(adapter.is_connected())

    def test_disconnect(self):
        """测试断开连接"""
        adapter = LocalDiskAdapter({'id': 'test'})
        adapter.connect()
        adapter.disconnect()
        self.assertFalse(adapter.is_connected())

    def test_scan(self):
        """测试文件扫描"""
        config = {
            'id': 'test',
            'mount_points': [self.temp_dir],
            'exclude_paths': []
        }

        adapter = LocalDiskAdapter(config)
        adapter.connect()

        files = list(adapter.scan(self.temp_dir, recursive=True))
        self.assertGreaterEqual(len(files), 2)

        paths = [f.path for f in files]
        self.assertIn(self.test_file, paths)
        self.assertIn(self.sub_file, paths)

    def test_compute_hash(self):
        """测试哈希计算"""
        config = {
            'id': 'test',
            'mount_points': [self.temp_dir]
        }

        adapter = LocalDiskAdapter(config)
        adapter.connect()

        hash_value = adapter.compute_hash(self.test_file, algorithm='sha256')
        self.assertIsInstance(hash_value, str)
        self.assertEqual(len(hash_value), 64)  # SHA-256 hex length

        # 验证哈希一致性
        hash_value2 = adapter.compute_hash(self.test_file, algorithm='sha256')
        self.assertEqual(hash_value, hash_value2)

    def test_get_info(self):
        """测试获取磁盘信息"""
        config = {
            'id': 'test',
            'mount_points': [self.temp_dir],
            'name': '测试磁盘'
        }

        adapter = LocalDiskAdapter(config)
        adapter.connect()

        info = adapter.get_info()
        self.assertEqual(info.name, '测试磁盘')
        self.assertEqual(info.storage_type, StorageType.LOCAL_DISK)
        self.assertGreater(info.total_size, 0)


class TestStorageManager(unittest.TestCase):
    """测试存储管理器"""

    def setUp(self):
        """创建测试环境"""
        self.temp_dir = tempfile.mkdtemp()

        # 创建测试文件
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("Test content")

    def tearDown(self):
        """清理测试环境"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_storage(self):
        """测试添加存储"""
        manager = StorageManager()

        storage_id = manager.add_storage('local_disk', {
            'id': 'test-disk',
            'name': '测试磁盘',
            'mount_points': [self.temp_dir]
        })

        self.assertIsNotNone(storage_id)
        self.assertEqual(storage_id, 'test-disk')

        # 清理
        manager.remove_storage(storage_id)

    def test_list_storages(self):
        """测试列出存储"""
        manager = StorageManager()

        storage_id = manager.add_storage('local_disk', {
            'id': 'test-list',
            'name': '列表测试',
            'mount_points': [self.temp_dir]
        })

        storages = manager.list_storages()
        self.assertIsInstance(storages, list)

        # 清理
        manager.remove_storage(storage_id)

    def test_remove_storage(self):
        """测试移除存储"""
        manager = StorageManager()

        storage_id = manager.add_storage('local_disk', {
            'id': 'test-remove',
            'name': '移除测试',
            'mount_points': [self.temp_dir]
        })

        result = manager.remove_storage(storage_id)
        self.assertTrue(result)

        # 验证已移除
        adapter = manager.get_storage(storage_id)
        self.assertIsNone(adapter)


if __name__ == '__main__':
    unittest.main()
