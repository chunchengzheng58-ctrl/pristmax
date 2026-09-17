# Pristmax 存储类型扩展实现方案

> 日期: 2026-09-16
> 版本: v1.0

## 目标

将 Pristmax 从单一硬盘存储优化扩展为支持多类型存储的统一存储优化平台，核心能力仍在本地硬盘，其他存储类型逐步拓展。

---

## 一、代码架构

### 1.1 目录结构

```
unified/
├── api.py                      # Flask API (扩展)
├── index.html                  # 前端页面
├── design.css                  # 样式
├── design.js                   # 前端逻辑
│
├── storage/                    # 存储抽象层 (新增)
│   ├── __init__.py            # 模块导出
│   ├── base.py                # 基类定义
│   ├── manager.py             # 存储管理器
│   ├── registry.py            # 适配器注册表
│   │
│   ├── adapters/              # 适配器实现
│   │   ├── __init__.py
│   │   ├── local_disk.py      # 本地硬盘 (SSD/HDD)
│   │   ├── nas.py             # NAS 存储 (SMB/NFS)
│   │   ├── usb.py             # USB/外置硬盘
│   │   ├── cloud.py           # 云存储 (S3)
│   │   └── raid.py            # RAID 阵列
│   │
│   └── scanners/              # 扫描引擎
│       ├── __init__.py
│       └── unified_scanner.py  # 统一扫描器
│
├── config/                    # 配置 (新增)
│   ├── __init__.py
│   └── storage_config.py       # 存储配置
│
├── tests/                     # 测试 (新增)
│   └── test_storage.py
│
└── docs/
    └── storage-expansion-plan.md
```

### 1.2 核心类设计

```
┌─────────────────────────────────────────────────────────────┐
│                       StorageAdapter (ABC)                    │
├─────────────────────────────────────────────────────────────┤
│  + storage_type: StorageType  {abstract}                    │
│  + storage_id: str                                        │
│  + storage_name: str                                      │
│  + connect(): bool {abstract}                             │
│  + disconnect(): void {abstract}                          │
│  + get_info(): StorageInfo {abstract}                     │
│  + scan(): Iterator[FileInfo] {abstract}                  │
│  + read_file(): bytes {abstract}                          │
│  + compute_hash(): str {abstract}                          │
└─────────────────────────────────────────────────────────────┘
           △                    △           △           △
           │                    │           │           │
    ┌──────────┐       ┌──────────┐ ┌──────────┐ ┌──────────┐
    │LocalDisk │       │   NAS    │ │   USB    │ │  Cloud   │
    │ Adapter  │       │ Adapter  │ │ Adapter  │ │ Adapter  │
    └──────────┘       └──────────┘ └──────────┘ └──────────┘

┌─────────────────────────────────────────────────────────────┐
│                      StorageManager (Singleton)              │
├─────────────────────────────────────────────────────────────┤
│  - _adapters: Dict[str, StorageAdapter]                     │
│  - _scan_tasks: Dict[str, ScanTask]                         │
│  - _registry: StorageRegistry                               │
│  + add_storage(type, config): str                          │
│  + remove_storage(id): bool                                │
│  + get_storage(id): StorageAdapter                         │
│  + list_storages(): List[dict]                             │
│  + scan_storage(id, path, recursive): Iterator[FileInfo]  │
│  + find_duplicates(ids): Dict[str, List[FileInfo]]         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     StorageRegistry (Singleton)               │
├─────────────────────────────────────────────────────────────┤
│  - _adapters: Dict[StorageType, Type[StorageAdapter]]      │
│  + register(type, adapter_class): void                     │
│  + unregister(type): bool                                   │
│  + get(type): Type[StorageAdapter]                          │
│  + create(type, config): StorageAdapter                    │
│  + list_registered(): List[StorageType]                    │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 数据模型

```python
# StorageType 枚举
class StorageType(Enum):
    LOCAL_DISK = "local_disk"
    NAS = "nas"
    USB = "usb"
    CLOUD = "cloud"
    RAID = "raid"

# StorageInfo 数据类
@dataclass
class StorageInfo:
    name: str
    storage_type: StorageType
    path: str
    total_size: int
    used_size: int
    free_size: int
    is_mounted: bool
    status: str  # healthy/error/offline
    metadata: Dict[str, Any]

# FileInfo 数据类
@dataclass
class FileInfo:
    path: str
    relative_path: str
    size: int
    modified_time: float
    hash: Optional[str]
    hash_algorithm: str
    storage_type: Optional[StorageType]
    is_directory: bool
    extension: str
```

---

## 二、适配器实现详情

### 2.1 LocalDiskAdapter (本地硬盘)

```python
class LocalDiskAdapter(StorageAdapter):
    def __init__(self, config: dict):
        self._mount_points = config.get('mount_points', [])
        self._exclude_paths = config.get('exclude_paths', [])
        self._exclude_extensions = config.get('exclude_extensions', [])
        self._min_file_size = config.get('min_file_size', 0)

    # 核心方法
    def scan(self, path, recursive, callback) -> Iterator[FileInfo]
    def compute_hash(self, path, algorithm, chunk_size) -> str
    def get_info(self) -> StorageInfo
```

**功能特性**:
- 多挂载点支持 (C:\, D:\, /home 等)
- Windows 系统路径自动排除 (Windows, System Volume Information 等)
- 权限错误自动跳过
- SHA-256/MD5/SHA-1 哈希支持

### 2.2 NASAdapter (网络存储)

```python
class NASAdapter(StorageAdapter):
    def __init__(self, config: dict):
        self.protocol = config.get('protocol', 'smb')  # smb | nfs
        self.host = config['host']
        self.share = config['share']
        self.username = config.get('username', 'guest')
        self.password = config.get('password', '')

    # 核心方法
    def connect() -> bool    # 挂载 SMB/NFS 共享
    def disconnect()         # 卸载共享
    def scan() -> Iterator[FileInfo]
```

**协议支持**:
| 协议 | Windows | Unix/Linux | 依赖 |
|------|---------|------------|------|
| SMB/CIFS | net use | mount -t cifs | smbclient |
| NFS | - | mount -t nfs | nfs-common |

### 2.3 USBAdapter (外置存储)

```python
class USBAdapter(StorageAdapter):
    def __init__(self, config: dict):
        self.auto_detect = config.get('auto_detect', True)
        self.device_id = config.get('device_id')

    # 核心方法
    def discover_devices() -> List[StorageInfo]  # 自动发现 USB 设备
    def connect() -> bool
    def eject() -> bool                          # 安全弹出
```

**特性**:
- 使用 psutil.disk_partitions() 检测可移动媒体
- Windows: 检查 `removable` 选项
- Unix/Linux: 检查 /sys/block/*/device 是否为 USB

### 2.4 CloudAdapter (云存储)

```python
class CloudAdapter(StorageAdapter):
    def __init__(self, config: dict):
        self.provider = config.get('provider', 'aws')  # aws|aliyun|tencent|minio
        self.bucket = config['bucket']
        self.region = config.get('region', 'us-east-1')
        self.access_key = config['access_key']
        self.secret_key = config['secret_key']
        self.endpoint = config.get('endpoint')  # MinIO 使用

    # 核心方法
    def scan() -> Iterator[FileInfo]  # ListObjectsV2
    def read_file(path, offset, size) -> bytes
    def compute_hash(path) -> str    # 使用 ETag (MD5)
```

**云服务商支持**:
| 提供商 | SDK | 认证方式 |
|--------|-----|----------|
| AWS S3 | boto3 | Access Key/Secret Key |
| 阿里云 OSS | oss2 | Access Key/Secret Key |
| 腾讯云 COS | qcloud_cos | SecretId/SecretKey |
| MinIO | boto3 | Access Key/Secret Key |

### 2.5 RAIDAdapter (RAID 阵列)

```python
class RAIDAdapter(StorageAdapter):
    def __init__(self, config: dict):
        self.raid_type = config.get('raid_type', 'megaraid')
        self.adapter_id = config.get('adapter_id', 0)

    # 核心方法
    def connect() -> bool
    def get_physical_drives() -> List[Dict]
    def get_logical_drives() -> List[Dict]
    def get_array_status() -> Dict
```

**RAID 类型支持**:
- MegaRAID (LSI) - 使用 storcli/perccli
- 硬件 RAID - 直接访问 /dev/sdX
- Intel RST
- Dell PERC
- HP Smart Array

---

## 三、API 扩展设计

### 3.1 REST API 端点

```
# 存储管理
GET    /api/storages              # 列出所有存储
POST   /api/storages              # 添加存储
DELETE /api/storages/<id>         # 移除存储
GET    /api/storages/<id>/info    # 获取存储详情
POST   /api/storages/<id>/refresh # 刷新存储状态

# 扫描操作
POST   /api/storages/<id>/scan    # 启动扫描
GET    /api/tasks/<task_id>       # 获取任务状态
GET    /api/tasks/<task_id>/files # 获取扫描结果

# 去重分析
POST   /api/duplicates/find       # 跨存储查找重复
GET    /api/duplicates            # 获取重复文件列表
```

### 3.2 请求/响应格式

```json
// POST /api/storages - 添加存储
Request:
{
  "type": "local_disk",
  "name": "本地磁盘 C:",
  "config": {
    "mount_points": ["C:\\"],
    "exclude_paths": ["C:\\Windows"]
  }
}

Response:
{
  "status": "ok",
  "storage_id": "local_disk-1694850000"
}

// GET /api/storages - 列出存储
Response:
{
  "storages": [
    {
      "id": "local-001",
      "name": "本地磁盘 (C:)",
      "type": "local_disk",
      "path": "C:\\",
      "total_size": 500105059200,
      "used_size": 234567890123,
      "free_size": 265537169077,
      "usage_percent": 46.9,
      "is_mounted": true,
      "status": "healthy"
    }
  ]
}
```

---

## 四、前端页面扩展

### 4.1 Dashboard 存储概览

```html
<div class="storage-overview">
  <div class="storage-card local-disk" data-storage-id="local-001">
    <div class="storage-icon">💾</div>
    <div class="storage-name">本地磁盘 (C:)</div>
    <div class="storage-usage">
      <div class="usage-bar">
        <div class="usage-fill" style="width: 47%"></div>
      </div>
      <div class="usage-text">234 GB / 500 GB (47%)</div>
    </div>
    <div class="storage-status healthy">● 正常</div>
  </div>

  <div class="storage-card nas" data-storage-id="nas-001">
    <div class="storage-icon">📡</div>
    <div class="storage-name">群晖 NAS</div>
    <div class="storage-usage">
      <div class="usage-bar">
        <div class="usage-fill" style="width: 57%"></div>
      </div>
      <div class="usage-text">1.1 TB / 2 TB (57%)</div>
    </div>
    <div class="storage-status healthy">● 正常</div>
  </div>
</div>
```

### 4.2 存储设置页面

```html
<div id="storage-settings" class="settings-section">
  <div class="section-header">
    <h2>存储管理</h2>
    <button class="btn-add-storage" onclick="openStorageWizard()">
      + 添加存储
    </button>
  </div>

  <!-- 存储类型选择向导 -->
  <div class="storage-wizard" id="storage-wizard">
    <div class="wizard-step" data-step="1">
      <h3>选择存储类型</h3>
      <div class="storage-type-grid">
        <button class="storage-type-btn" data-type="local_disk">
          <span class="icon">💾</span>
          <span class="label">本地硬盘</span>
          <span class="desc">SSD / HDD 磁盘</span>
        </button>
        <button class="storage-type-btn" data-type="nas">
          <span class="icon">📡</span>
          <span class="label">NAS 存储</span>
          <span class="desc">SMB / NFS 网络共享</span>
        </button>
        <button class="storage-type-btn" data-type="usb">
          <span class="icon">🔌</span>
          <span class="label">外置硬盘</span>
          <span class="desc">USB 存储设备</span>
        </button>
        <button class="storage-type-btn" data-type="cloud">
          <span class="icon">☁️</span>
          <span class="label">云存储</span>
          <span class="desc">S3 兼容存储</span>
        </button>
      </div>
    </div>

    <div class="wizard-step hidden" data-step="2">
      <!-- 动态表单，根据存储类型显示不同配置 -->
    </div>
  </div>
</div>
```

---

## 五、配置管理

### 5.1 配置文件结构 (config/storages.json)

```json
{
  "version": "1.0",
  "storages": [
    {
      "id": "local-001",
      "name": "本地磁盘 (C:)",
      "type": "local_disk",
      "enabled": true,
      "config": {
        "mount_points": ["C:\\"],
        "exclude_paths": [
          "C:\\Windows",
          "C:\\$Recycle.Bin",
          "C:\\System Volume Information"
        ],
        "min_file_size": 1024
      }
    },
    {
      "id": "nas-001",
      "name": "群晖 NAS",
      "type": "nas",
      "enabled": true,
      "config": {
        "protocol": "smb",
        "host": "192.168.1.100",
        "share": "shared",
        "username": "admin",
        "password": "encrypted_password"
      }
    },
    {
      "id": "usb-001",
      "name": "外置硬盘",
      "type": "usb",
      "enabled": true,
      "config": {
        "auto_detect": true
      }
    }
  ],
  "settings": {
    "scan": {
      "default_recursive": true,
      "min_file_size": 1024,
      "hash_algorithm": "sha256"
    },
    "dedup": {
      "enabled": true,
      "min_duplicate_size": 1024
    }
  }
}
```

---

## 六、实现阶段

| 阶段 | 内容 | 文件 | 工作量 |
|------|------|------|--------|
| **Phase 0** | 架构基础设施 | base.py, registry.py, manager.py | 2天 |
| **Phase 1** | 本地硬盘适配器 | local_disk.py | 1天 |
| **Phase 2** | NAS 适配器 | nas.py | 2天 |
| **Phase 3** | USB 适配器 | usb.py | 1天 |
| **Phase 4** | 云存储适配器 | cloud.py | 3天 |
| **Phase 5** | RAID 适配器 | raid.py | 2天 |
| **Phase 6** | 前端页面 | index.html, design.css | 2天 |
| **Phase 7** | API 集成 | api.py | 1天 |

**总计**: 约 14 个工作日

---

## 七、文件清单

| 文件路径 | 说明 | 行数 |
|---------|------|-----|
| storage/__init__.py | 模块导出 | ~30 |
| storage/base.py | 基类和数据模型 | ~280 |
| storage/registry.py | 适配器注册表 | ~120 |
| storage/manager.py | 存储管理器 | ~380 |
| storage/adapters/__init__.py | 适配器导出 | ~15 |
| storage/adapters/local_disk.py | 本地硬盘 | ~280 |
| storage/adapters/nas.py | NAS 存储 | ~350 |
| storage/adapters/usb.py | USB 存储 | ~280 |
| storage/adapters/cloud.py | 云存储 | ~400 |
| storage/adapters/raid.py | RAID 阵列 | ~400 |
| storage/scanners/__init__.py | 扫描器导出 | ~10 |
| storage/scanners/unified_scanner.py | 统一扫描器 | ~350 |
| config/__init__.py | 配置导出 | ~10 |
| config/storage_config.py | 存储配置 | ~250 |
| tests/test_storage.py | 单元测试 | ~350 |
