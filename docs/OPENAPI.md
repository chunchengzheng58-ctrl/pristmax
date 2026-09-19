# Pristmax OpenAPI 文档

**版本**: 1.0.0
**基础URL**: `https://api.jiangchenghehe.top` (生产) 或 `http://localhost:5001` (本地)

---

## 认证

### API Key 认证

```http
Authorization: Bearer YOUR_API_KEY
```

获取 API Key: POST `/api/auth/apikey/login`

---

## 存储管理

### 获取存储列表

```http
GET /api/storages
```

**响应**:
```json
{
  "storages": [
    {
      "id": "local-001",
      "name": "本地磁盘 C:",
      "type": "local",
      "total_size": 500000000000,
      "used_size": 250000000000,
      "path": "C:\\"
    }
  ]
}
```

### 添加存储卷

```http
POST /api/storages
Content-Type: application/json

{
  "name": "我的NAS",
  "type": "nas",
  "path": "//192.168.1.100/share",
  "config": {
    "protocol": "smb",
    "username": "user",
    "password": "pass"
  }
}
```

---

## 任务管理

### 创建任务

```http
POST /api/tasks
Content-Type: application/json

{
  "type": "scan",
  "params": {
    "storage_id": "local-001",
    "path": "/data"
  },
  "priority": "normal"
}
```

**响应**:
```json
{
  "task_id": "task-123",
  "status": "pending",
  "created_at": "2026-09-19T12:00:00Z"
}
```

### 获取任务状态

```http
GET /api/tasks/{task_id}
```

### SSE 实时进度

```http
GET /api/tasks/{task_id}/stream
```

**事件流**:
```
data: {"status": "running", "progress": 45}

data: {"status": "completed", "result": {...}}
```

---

## Storage Agent API

### 获取统计

```http
GET /api/agent/stats?path=/data
```

**响应**:
```json
{
  "total_files": 12847,
  "total_size": 128500000000,
  "total_size_display": "119.7 GB",
  "by_category": {
    "video": {"count": 1200, "size": 87000000000, "size_display": "81.0 GB"},
    "image": {"count": 4500, "size": 12000000000, "size_display": "11.2 GB"}
  }
}
```

### 查找大文件

```http
GET /api/agent/large-files?path=/data&min=100
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| path | string | 目录路径 |
| min | int | 最小大小(MB)，默认100 |
| limit | int | 返回数量，默认20 |

### 查找重复文件

```http
GET /api/agent/duplicates?path=/data&min=1
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| path | string | 目录路径 |
| min | int | 最小大小(KB)，默认1 |

### 综合分析

```http
POST /api/agent/analyze
Content-Type: application/json

{
  "path": "/data",
  "include_suggestions": true
}
```

---

## 错误码

| 错误码 | 说明 |
|--------|------|
| 400 | 参数错误 |
| 401 | 未认证 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

---

## 速率限制

| 等级 | 请求/分钟 |
|------|-----------|
| 免费 | 60 |
| 专业版 | 600 |
| 企业版 | 6000 |

---

## SDK

### Python

```bash
pip install requests

import requests

API_KEY = "your-api-key"
BASE_URL = "https://api.jiangchenghehe.top"

headers = {"Authorization": f"Bearer {API_KEY}"}

# 获取统计
response = requests.get(
    f"{BASE_URL}/api/agent/stats",
    params={"path": "/data"},
    headers=headers
)
print(response.json())
```

### JavaScript

```javascript
const API_KEY = 'your-api-key';
const BASE_URL = 'https://api.jiangchenghehe.top';

const response = await fetch(
  `${BASE_URL}/api/agent/stats?path=/data`,
  { headers: { 'Authorization': `Bearer ${API_KEY}` } }
);
const data = await response.json();
console.log(data);
```
