"""
Storage Agent MCP Server (安全增强版)

MCP (Model Context Protocol) Server for Storage Agent.
支持审批流程、安全控制和完整审计。

Usage:
    # As standalone server
    python -m src.pristmax.agent.mcp_server

    # Or integrate with Claude Code via:
    # claude_desktop_config.json
"""

import json
import sys
import io
import os
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.pristmax.agent.storage_agent import (
    StorageAgent,
    SecurityConfig,
    _security_config,
    set_security_config,
    OperationStatus,
    OperationType,
    ApprovalManager,
    AuditLogger
)

# MCP Protocol Constants
JSONRPC_VERSION = "2.0"
MCP_VERSION = "2024-11-05"


class MCPProtocol:
    """MCP Protocol Handler"""

    @staticmethod
    def parse_request(line: str) -> dict:
        """Parse incoming JSON-RPC request"""
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"jsonrpc": JSONRPC_VERSION, "error": {"code": -32700, "message": "Parse error"}, "id": None}

    @staticmethod
    def response(id, result: dict) -> str:
        """Create JSON-RPC success response"""
        return json.dumps({
            "jsonrpc": JSONRPC_VERSION,
            "id": id,
            "result": result
        })

    @staticmethod
    def error(id, code: int, message: str) -> str:
        """Create JSON-RPC error response"""
        return json.dumps({
            "jsonrpc": JSONRPC_VERSION,
            "id": id,
            "error": {"code": code, "message": message}
        })


class StorageAgentMCPServer:
    """Storage Agent MCP Server (安全增强版)"""

    def __init__(self, db_path: str = ":memory:"):
        self.agent = StorageAgent(db_path=db_path)
        self.protocol = MCPProtocol()
        self._tool_handlers = self._register_tools()

    def _register_tools(self) -> dict:
        """Register available tools"""
        return {
            # 只读操作
            "storage_stats": self._handle_stats,
            "storage_large_files": self._handle_large_files,
            "storage_duplicates": self._handle_duplicates,
            "storage_suggestions": self._handle_suggestions,
            "storage_analyze": self._handle_analyze,
            "storage_cleanup_summary": self._handle_cleanup_summary,
            "storage_chat": self._handle_chat,

            # 预览操作（dry-run，无需审批）
            "storage_cleanup_preview": self._handle_cleanup_preview,

            # 审批流程
            "storage_approval_list": self._handle_approval_list,
            "storage_approval_query": self._handle_approval_query,
            "storage_approval_action": self._handle_approval_action,

            # 安全配置
            "storage_security_config": self._handle_security_config,
            "storage_security_status": self._handle_security_status,

            # 审计日志
            "storage_audit_log": self._handle_audit_log,

            # 缓存管理
            "storage_cache_clear": self._handle_cache_clear,
            "storage_cache_status": self._handle_cache_status,

            # 进度查询
            "storage_progress": self._handle_progress,
            "storage_progress_list": self._handle_progress_list,

            # 文件监控
            "storage_monitor_start": self._handle_monitor_start,
            "storage_monitor_stop": self._handle_monitor_stop,
            "storage_monitor_changes": self._handle_monitor_changes,
            "storage_incremental_scan": self._handle_incremental_scan,
            # 内容搜索
            "storage_search_content": self._handle_search_content,
            # 定时任务
            "storage_schedule_add": self._handle_schedule_add,
            "storage_schedule_remove": self._handle_schedule_remove,
            "storage_schedule_list": self._handle_schedule_list,
            # 云存储
            "storage_cloud_config": self._handle_cloud_config,
            "storage_cloud_status": self._handle_cloud_status,
            "storage_cloud_upload": self._handle_cloud_upload,
            "storage_cloud_download": self._handle_cloud_download,
            "storage_cloud_sync": self._handle_cloud_sync,
            # 桌面同步
            "storage_sync_save": self._handle_sync_save,
            "storage_sync_list": self._handle_sync_list,
            "storage_sync_to_cloud": self._handle_sync_to_cloud,
            "storage_sync_from_cloud": self._handle_sync_from_cloud,
            # 系统管理
            "storage_health": self._handle_health,
            "storage_cache_stats": self._handle_cache_stats,
            "storage_history": self._handle_history,
            "storage_clear_expired": self._handle_clear_expired,
        }

    def get_tools_list(self) -> list:
        """Return list of available tools for MCP"""
        return [
            # ===== 只读操作 =====
            {
                "name": "storage_stats",
                "description": "获取目录存储统计（只读操作，无需审批）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                        "incremental": {"type": "boolean", "description": "使用增量扫描", "default": True}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_large_files",
                "description": "查找大文件（只读操作，无需审批）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                        "min_size_mb": {"type": "integer", "description": "最小文件大小(MB)", "default": 100},
                        "limit": {"type": "integer", "description": "返回数量", "default": 20},
                        "offset": {"type": "integer", "description": "分页偏移", "default": 0}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_duplicates",
                "description": "查找重复文件（只读操作，无需审批）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                        "min_size_kb": {"type": "integer", "description": "最小文件大小(KB)", "default": 1}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_suggestions",
                "description": "获取优化建议（只读操作，无需审批）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_analyze",
                "description": "综合存储分析（只读操作，无需审批）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_cleanup_summary",
                "description": "获取智能清理摘要（用于饼图展示）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_chat",
                "description": "自然语言对话（只读操作，无需审批）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                        "question": {"type": "string", "description": "问题"}
                    },
                    "required": ["path", "question"]
                }
            },

            # ===== 预览操作（dry-run）=====
            {
                "name": "storage_cleanup_preview",
                "description": "预览清理操作（不实际删除，仅预览）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                        "type": {"type": "string", "enum": ["duplicates", "large"], "description": "清理类型"},
                        "min_size_mb": {"type": "integer", "description": "大文件最小大小(MB)", "default": 100}
                    },
                    "required": ["path", "type"]
                }
            },

            # ===== 审批流程 =====
            {
                "name": "storage_approval_list",
                "description": "列出所有操作记录",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["pending", "approved", "rejected", "completed", "failed"], "description": "状态筛选"},
                        "limit": {"type": "integer", "description": "返回数量", "default": 50}
                    }
                }
            },
            {
                "name": "storage_approval_query",
                "description": "查询待审批操作",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["pending", "approved", "rejected"], "description": "状态筛选"}
                    }
                }
            },
            {
                "name": "storage_approval_action",
                "description": "审批操作（批准/拒绝）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "operation_id": {"type": "string", "description": "操作ID"},
                        "action": {"type": "string", "enum": ["approve", "reject"], "description": "审批动作"},
                        "approved_by": {"type": "string", "description": "审批人", "default": "mcp_user"}
                    },
                    "required": ["operation_id", "action"]
                }
            },

            # ===== 安全配置 =====
            {
                "name": "storage_security_config",
                "description": "配置安全策略",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "allowed_paths": {"type": "array", "items": {"type": "string"}, "description": "允许访问的路径列表"},
                        "readonly": {"type": "boolean", "description": "只读模式"},
                        "require_approval": {"type": "boolean", "description": "是否需要审批"},
                        "max_files": {"type": "integer", "description": "最大扫描文件数"},
                        "max_size_gb": {"type": "integer", "description": "最大扫描大小(GB)"},
                        "parallel_enabled": {"type": "boolean", "description": "启用并行扫描"},
                        "parallel_threads": {"type": "integer", "description": "并行线程数"}
                    }
                }
            },
            {
                "name": "storage_security_status",
                "description": "查看当前安全配置状态",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },

            # ===== 审计日志 =====
            {
                "name": "storage_audit_log",
                "description": "查看审计日志",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "level": {"type": "string", "enum": ["INFO", "WARNING", "ERROR"], "description": "日志级别"},
                        "operation": {"type": "string", "description": "操作类型"},
                        "limit": {"type": "integer", "description": "返回数量", "default": 100}
                    }
                }
            },

            # ===== 缓存管理 =====
            {
                "name": "storage_cache_clear",
                "description": "清除扫描缓存",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "清除指定路径缓存（不填则清除所有）"}
                    }
                }
            },
            {
                "name": "storage_cache_status",
                "description": "查看缓存状态",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },

            # ===== 进度查询 =====
            {
                "name": "storage_progress",
                "description": "查询扫描进度",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "scan_id": {"type": "string", "description": "扫描任务ID"}
                    }
                }
            },
            {
                "name": "storage_progress_list",
                "description": "列出所有扫描任务",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            # ===== 文件监控 =====
            {
                "name": "storage_monitor_start",
                "description": "启动文件监控",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "要监控的目录路径"},
                        "recursive": {"type": "boolean", "description": "是否递归监控子目录", "default": True}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_monitor_stop",
                "description": "停止文件监控",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "monitor_id": {"type": "string", "description": "监控会话ID"}
                    }
                }
            },
            {
                "name": "storage_monitor_changes",
                "description": "获取监控期间的文件变化",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "monitor_id": {"type": "string", "description": "监控会话ID"}
                    },
                    "required": ["monitor_id"]
                }
            },
            {
                "name": "storage_incremental_scan",
                "description": "增量扫描，检测新增/修改/删除的文件",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                        "since_mtime": {"type": "number", "description": "起始时间戳（Unix时间戳）"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_search_content",
                "description": "搜索文件内容（支持正则表达式）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "搜索根目录"},
                        "keyword": {"type": "string", "description": "搜索关键字或正则表达式"},
                        "file_types": {"type": "array", "items": {"type": "string"}, "description": "要搜索的文件类型扩展名", "default": [".txt", ".py", ".js", ".json"]},
                        "max_results": {"type": "integer", "description": "最大结果数", "default": 100}
                    },
                    "required": ["path", "keyword"]
                }
            },
            # ===== 定时任务 =====
            {
                "name": "storage_schedule_add",
                "description": "添加定时扫描任务",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "任务ID"},
                        "path": {"type": "string", "description": "要扫描的路径"},
                        "schedule": {"type": "string", "description": "Cron表达式，如 '0 2 * * *'（每天凌晨2点）"},
                        "task_type": {"type": "string", "enum": ["stats", "duplicates", "large"], "description": "任务类型", "default": "stats"}
                    },
                    "required": ["task_id", "path", "schedule"]
                }
            },
            {
                "name": "storage_schedule_remove",
                "description": "移除定时任务",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "任务ID"}
                    },
                    "required": ["task_id"]
                }
            },
            {
                "name": "storage_schedule_list",
                "description": "列出所有定时任务",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            # ===== 云存储 =====
            {
                "name": "storage_cloud_config",
                "description": "配置云存储（S3/OSS/MinIO）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string", "enum": ["s3", "oss"], "description": "云提供商"},
                        "access_key": {"type": "string", "description": "访问密钥"},
                        "secret_key": {"type": "string", "description": "秘密密钥"},
                        "bucket": {"type": "string", "description": "存储桶名称"},
                        "region": {"type": "string", "description": "区域（如 s3）或 endpoint（如 oss）"},
                        "endpoint": {"type": "string", "description": "自定义端点（可选）"}
                    },
                    "required": ["provider", "access_key", "secret_key", "bucket"]
                }
            },
            {
                "name": "storage_cloud_status",
                "description": "获取云存储状态",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string", "enum": ["s3", "oss"], "description": "云提供商", "default": "s3"}
                    }
                }
            },
            {
                "name": "storage_cloud_upload",
                "description": "上传文件到云存储",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "local_path": {"type": "string", "description": "本地文件路径"},
                        "cloud_path": {"type": "string", "description": "云存储路径"},
                        "provider": {"type": "string", "enum": ["s3", "oss"], "description": "云提供商", "default": "s3"}
                    },
                    "required": ["local_path", "cloud_path"]
                }
            },
            {
                "name": "storage_cloud_download",
                "description": "从云存储下载文件",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cloud_path": {"type": "string", "description": "云存储路径"},
                        "local_path": {"type": "string", "description": "本地保存路径"},
                        "provider": {"type": "string", "enum": ["s3", "oss"], "description": "云提供商", "default": "s3"}
                    },
                    "required": ["cloud_path", "local_path"]
                }
            },
            {
                "name": "storage_cloud_sync",
                "description": "同步本地目录到云存储",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "local_path": {"type": "string", "description": "本地目录路径"},
                        "cloud_prefix": {"type": "string", "description": "云存储前缀路径"},
                        "provider": {"type": "string", "enum": ["s3", "oss"], "description": "云提供商", "default": "s3"}
                    },
                    "required": ["local_path", "cloud_prefix"]
                }
            },
            # ===== 桌面同步 =====
            {
                "name": "storage_sync_save",
                "description": "保存扫描结果到本地同步库",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "扫描路径"},
                        "scan_result": {"type": "object", "description": "扫描结果"}
                    },
                    "required": ["path", "scan_result"]
                }
            },
            {
                "name": "storage_sync_list",
                "description": "列出已同步的路径",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "storage_sync_to_cloud",
                "description": "同步本地记录到云端",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string", "enum": ["s3", "oss"], "description": "云提供商", "default": "s3"}
                    }
                }
            },
            {
                "name": "storage_sync_from_cloud",
                "description": "从云端恢复同步数据",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string", "enum": ["s3", "oss"], "description": "云提供商", "default": "s3"}
                    }
                }
            },
            # ===== 系统管理 =====
            {
                "name": "storage_health",
                "description": "健康检查，返回系统状态",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "storage_cache_stats",
                "description": "获取缓存统计信息",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "storage_history",
                "description": "获取扫描历史记录",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "返回数量", "default": 20}
                    }
                }
            },
            {
                "name": "storage_clear_expired",
                "description": "清理过期缓存",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

    # ===== 只读操作处理 =====

    def _handle_stats(self, params: dict) -> dict:
        """Handle storage_stats tool call"""
        path = params.get("path", ".")
        incremental = params.get("incremental", True)
        stats = self.agent.get_storage_stats(path, incremental=incremental)
        return stats

    def _handle_large_files(self, params: dict) -> dict:
        """Handle storage_large_files tool call"""
        path = params.get("path", ".")
        min_mb = params.get("min_size_mb", 100)
        limit = params.get("limit", 20)
        offset = params.get("offset", 0)
        result = self.agent.analyze_large_files(path, min_size_mb=min_mb, limit=limit, offset=offset)
        if isinstance(result, dict):
            return {
                "files": [{"path": f.path, "size": f.size, "size_display": f.size_display} for f in result.get('items', [])],
                "total": result.get('total', 0),
                "offset": result.get('offset', 0),
                "limit": result.get('limit', limit),
                "has_more": result.get('has_more', False)
            }
        return {
            "files": [{"path": f.path, "size": f.size, "size_display": f.size_display} for f in result],
            "count": len(result)
        }

    def _handle_duplicates(self, params: dict) -> dict:
        """Handle storage_duplicates tool call"""
        path = params.get("path", ".")
        min_kb = params.get("min_size_kb", 1)
        duplicates = self.agent.find_duplicates(path, min_size_kb=min_kb)
        return {
            "groups": [
                {
                    "count": g.count,
                    "size_display": g.size_display,
                    "wasted_space": g.wasted_space,
                    "files": g.files
                } for g in duplicates[:10]
            ],
            "total_groups": len(duplicates)
        }

    def _handle_suggestions(self, params: dict) -> dict:
        """Handle storage_suggestions tool call"""
        path = params.get("path", ".")
        suggestions = self.agent.get_suggestions(path)
        return {"suggestions": suggestions}

    def _handle_analyze(self, params: dict) -> dict:
        """Handle storage_analyze tool call"""
        path = params.get("path", ".")
        stats = self.agent.get_storage_stats(path, incremental=True)
        suggestions = self.agent.get_suggestions(path)
        cleanup_summary = self.agent.get_cleanup_summary(path)
        return {"stats": stats, "suggestions": suggestions, "cleanup": cleanup_summary}

    def _handle_cleanup_summary(self, params: dict) -> dict:
        """Handle storage_cleanup_summary tool call"""
        path = params.get("path", ".")
        summary = self.agent.get_cleanup_summary(path)
        return summary

    def _handle_chat(self, params: dict) -> dict:
        """Handle storage_chat tool call"""
        path = params.get("path", ".")
        question = params.get("question", "")
        response = self.agent.chat(path, question)
        return {"response": response}

    # ===== 预览操作处理 =====

    def _handle_cleanup_preview(self, params: dict) -> dict:
        """Handle cleanup preview - always dry-run"""
        path = params.get("path", ".")
        cleanup_type = params.get("type", "duplicates")
        min_size_mb = params.get("min_size_mb", 100)

        if cleanup_type == "duplicates":
            result = self.agent.cleanup_duplicates(path, dry_run=True, auto_approve=True)
        elif cleanup_type == "large":
            result = self.agent.cleanup_large_files(path, min_size_mb=min_size_mb, dry_run=True, auto_approve=True)
        elif cleanup_type == "temp":
            temp_files = self.agent._find_temp_files(path)
            result = {
                'type': 'temp',
                'files': temp_files['files'],
                'count': temp_files['count'],
                'size': temp_files['size'],
                'dry_run': True,
                'warning': '这是预览模式，实际删除需要审批'
            }
        elif cleanup_type == "old":
            old_files = self.agent._find_old_files(path, days=365)
            result = {
                'type': 'old',
                'files': old_files['files'],
                'count': old_files['count'],
                'size': old_files['size'],
                'dry_run': True,
                'warning': '这是预览模式，实际删除需要审批'
            }
        elif cleanup_type == "empty":
            empty_folders = self.agent._find_empty_folders(path)
            result = {
                'type': 'empty',
                'folders': empty_folders['folders'],
                'count': empty_folders['count'],
                'dry_run': True,
                'warning': '这是预览模式，实际删除需要审批'
            }
        else:
            result = {'error': f'Unknown cleanup type: {cleanup_type}'}

        return result

    # ===== 审批流程处理 =====

    def _handle_approval_list(self, params: dict) -> dict:
        """Handle approval list"""
        status_str = params.get("status")
        limit = params.get("limit", 50)

        status = None
        if status_str:
            try:
                status = OperationStatus(status_str)
            except ValueError:
                return {"error": f"Invalid status: {status_str}"}

        operations = self.agent.approval_manager.list_operations(status=status, limit=limit)
        return {
            "operations": [op.to_dict() for op in operations],
            "count": len(operations)
        }

    def _handle_approval_query(self, params: dict) -> dict:
        """Handle approval query - get pending operations"""
        status_str = params.get("status", "pending")

        try:
            status = OperationStatus(status_str)
        except ValueError:
            return {"error": f"Invalid status: {status_str}"}

        operations = self.agent.approval_manager.list_operations(status=status, limit=100)
        return {
            "operations": [op.to_dict() for op in operations],
            "count": len(operations),
            "status": status_str
        }

    def _handle_approval_action(self, params: dict) -> dict:
        """Handle approval action - approve or reject"""
        operation_id = params.get("operation_id")
        action = params.get("action")
        approved_by = params.get("approved_by", "mcp_user")

        if not operation_id:
            return {"error": "operation_id is required"}
        if action not in ["approve", "reject"]:
            return {"error": "action must be 'approve' or 'reject'"}

        # 检查操作是否存在
        op = self.agent.approval_manager.get_operation(operation_id)
        if not op:
            return {"error": f"Operation not found: {operation_id}"}

        if op.status != OperationStatus.PENDING:
            return {"error": f"Operation is not pending: {op.status.value}"}

        if action == "approve":
            success = self.agent.approval_manager.approve(operation_id, approved_by)
            if success:
                # 执行已批准的操作
                return self._execute_approved_operation(operation_id)
            return {"error": "Failed to approve operation"}
        else:
            success = self.agent.approval_manager.reject(operation_id, approved_by)
            return {"success": success, "action": "rejected", "operation_id": operation_id}

    def _execute_approved_operation(self, operation_id: str) -> dict:
        """执行已批准的操作"""
        op = self.agent.approval_manager.get_operation(operation_id)
        if not op:
            return {"error": "Operation not found"}

        try:
            if op.type == OperationType.DELETE_DUPLICATES:
                result = self.agent.cleanup_duplicates(
                    op.path,
                    dry_run=False,
                    auto_approve=True
                )
            elif op.type == OperationType.DELETE_FILES:
                min_size_mb = op.params.get('min_size_mb', 100)
                result = self.agent.cleanup_large_files(
                    op.path,
                    min_size_mb=min_size_mb,
                    dry_run=False,
                    auto_approve=True
                )
            else:
                result = {"error": f"Unknown operation type: {op.type}"}

            self.agent.approval_manager.complete(operation_id, result=result)
            return {
                "success": True,
                "operation_id": operation_id,
                "result": result
            }
        except Exception as e:
            self.agent.approval_manager.complete(operation_id, error=str(e))
            return {"error": str(e)}

    # ===== 安全配置处理 =====

    def _handle_security_config(self, params: dict) -> dict:
        """Handle security config"""
        allowed_paths = params.get("allowed_paths")
        readonly = params.get("readonly")
        require_approval = params.get("require_approval")
        max_files = params.get("max_files")
        max_size_gb = params.get("max_size_gb")
        parallel_enabled = params.get("parallel_enabled")
        parallel_threads = params.get("parallel_threads")

        if allowed_paths is not None:
            _security_config.allowed_paths = allowed_paths
        if readonly is not None:
            _security_config.readonly_mode = readonly
        if require_approval is not None:
            _security_config.require_approval = require_approval
        if max_files is not None:
            _security_config.max_scan_files = max_files
        if max_size_gb is not None:
            _security_config.max_scan_size_gb = max_size_gb
        if parallel_enabled is not None:
            _security_config.parallel_enabled = parallel_enabled
        if parallel_threads is not None:
            _security_config.parallel_threads = parallel_threads

        return {
            "success": True,
            "config": {
                "allowed_paths": _security_config.allowed_paths,
                "readonly_mode": _security_config.readonly_mode,
                "require_approval": _security_config.require_approval,
                "max_scan_files": _security_config.max_scan_files,
                "max_scan_size_gb": _security_config.max_scan_size_gb,
                "parallel_enabled": _security_config.parallel_enabled,
                "parallel_threads": _security_config.parallel_threads
            }
        }

    def _handle_security_status(self, params: dict) -> dict:
        """Handle security status"""
        return {
            "config": {
                "allowed_paths": _security_config.allowed_paths,
                "readonly_mode": _security_config.readonly_mode,
                "require_approval": _security_config.require_approval,
                "max_scan_files": _security_config.max_scan_files,
                "max_scan_size_gb": _security_config.max_scan_size_gb,
                "parallel_enabled": _security_config.parallel_enabled,
                "parallel_threads": _security_config.parallel_threads,
                "max_scan_size_gb": _security_config.max_scan_size_gb,
                "max_operation_time": _security_config.max_operation_time,
                "max_file_size_mb": _security_config.max_file_size_mb,
                "high_risk_confirm": _security_config.high_risk_confirm
            },
            "readonly_mode_active": _security_config.readonly_mode,
            "approval_required": _security_config.require_approval
        }

    # ===== 审计日志处理 =====

    def _handle_audit_log(self, params: dict) -> dict:
        """Handle audit log query"""
        # 简化实现，实际应该查询数据库
        return {
            "message": "审计日志功能需要持久化存储",
            "hint": "使用 --db 参数启动服务器以保存审计日志"
        }

    # ===== 缓存管理处理 =====

    def _handle_cache_clear(self, params: dict) -> dict:
        """Handle cache clear"""
        path = params.get("path")
        if path:
            self.agent.clear_cache(path)
            return {"success": True, "message": f"已清除路径 {path} 的缓存"}
        else:
            self.agent.clear_cache()
            return {"success": True, "message": "已清除所有缓存"}

    def _handle_cache_status(self, params: dict) -> dict:
        """Handle cache status"""
        try:
            cursor = self.agent.conn.execute('SELECT COUNT(*), MAX(expires_at) FROM scan_cache')
            row = cursor.fetchone()
            count = row[0] if row else 0
            max_expires = row[1] if row and row[1] else None
            return {
                "cache_enabled": self.agent.cache_enabled,
                "cache_ttl_seconds": self.agent.cache_ttl_seconds,
                "cached_paths": count,
                "oldest_expires": max_expires
            }
        except Exception as e:
            return {"error": str(e)}

    def _handle_progress(self, params: dict) -> dict:
        """Handle progress query"""
        from src.pristmax.agent.storage_agent import ScanProgressTracker
        scan_id = params.get("scan_id")
        if not scan_id:
            return {"error": "scan_id is required"}
        progress = ScanProgressTracker.get(scan_id)
        if not progress:
            return {"error": f"Scan {scan_id} not found", "scan_id": scan_id}
        return {"scan_id": scan_id, **progress}

    def _handle_progress_list(self, params: dict) -> dict:
        """Handle progress list"""
        from src.pristmax.agent.storage_agent import ScanProgressTracker
        ScanProgressTracker.cleanup_old()
        return {"tasks": ScanProgressTracker.list_all()}

    # ===== 文件监控处理 =====

    def _handle_monitor_start(self, params: dict) -> dict:
        """Handle storage_monitor_start"""
        path = params.get("path", "")
        recursive = params.get("recursive", True)
        monitor_id = self.agent.start_monitoring(path, recursive=recursive)
        if monitor_id:
            return {
                "monitor_id": monitor_id,
                "status": "started",
                "path": path
            }
        return {"error": "Failed to start monitoring. Please install watchdog: pip install watchdog", "status": "error"}

    def _handle_monitor_stop(self, params: dict) -> dict:
        """Handle storage_monitor_stop"""
        monitor_id = params.get("monitor_id")
        return self.agent.stop_monitoring(monitor_id)

    def _handle_monitor_changes(self, params: dict) -> dict:
        """Handle storage_monitor_changes"""
        monitor_id = params.get("monitor_id", "")
        return {
            "monitor_id": monitor_id,
            "changes": self.agent.get_monitoring_changes(monitor_id)
        }

    def _handle_incremental_scan(self, params: dict) -> dict:
        """Handle storage_incremental_scan"""
        path = params.get("path", "")
        since_mtime = params.get("since_mtime")
        return self.agent.get_incremental_changes(path, since_mtime)

    def _handle_search_content(self, params: dict) -> dict:
        """Handle storage_search_content"""
        path = params.get("path", "")
        keyword = params.get("keyword", "")
        file_types = params.get("file_types")
        max_results = params.get("max_results", 100)
        return self.agent.search_file_content(path, keyword, file_types, max_results)

    def _handle_schedule_add(self, params: dict) -> dict:
        """Handle storage_schedule_add"""
        from src.pristmax.agent.storage_agent import ScheduledTaskManager
        task_id = params.get("task_id", "")
        path = params.get("path", "")
        schedule = params.get("schedule", "")
        task_type = params.get("task_type", "stats")
        manager = ScheduledTaskManager()
        return manager.add_scan_task(task_id, path, schedule, task_type)

    def _handle_schedule_remove(self, params: dict) -> dict:
        """Handle storage_schedule_remove"""
        from src.pristmax.agent.storage_agent import ScheduledTaskManager
        task_id = params.get("task_id", "")
        manager = ScheduledTaskManager()
        return manager.remove_task(task_id)

    def _handle_schedule_list(self, params: dict) -> dict:
        """Handle storage_schedule_list"""
        from src.pristmax.agent.storage_agent import ScheduledTaskManager
        manager = ScheduledTaskManager()
        return {"tasks": manager.list_tasks()}

    # ===== 云存储处理 =====

    def _handle_cloud_config(self, params: dict) -> dict:
        """Handle storage_cloud_config"""
        from src.pristmax.agent.storage_agent import CloudStorageManager
        provider = params.get("provider", "s3")
        access_key = params.get("access_key", "")
        secret_key = params.get("secret_key", "")
        bucket = params.get("bucket", "")
        region = params.get("region", "us-east-1")
        endpoint = params.get("endpoint")

        manager = CloudStorageManager()
        if provider == "oss":
            return manager.configure_oss(access_key, secret_key, bucket, region)  # region is endpoint for OSS
        else:
            return manager.configure_s3(access_key, secret_key, bucket, region, endpoint)

    def _handle_cloud_status(self, params: dict) -> dict:
        """Handle storage_cloud_status"""
        from src.pristmax.agent.storage_agent import CloudStorageManager
        provider = params.get("provider", "s3")
        manager = CloudStorageManager()
        return manager.get_status(provider)

    def _handle_cloud_upload(self, params: dict) -> dict:
        """Handle storage_cloud_upload"""
        from src.pristmax.agent.storage_agent import CloudStorageManager
        local_path = params.get("local_path", "")
        cloud_path = params.get("cloud_path", "")
        provider = params.get("provider", "s3")
        manager = CloudStorageManager()
        return manager.upload_file(local_path, cloud_path, provider)

    def _handle_cloud_download(self, params: dict) -> dict:
        """Handle storage_cloud_download"""
        from src.pristmax.agent.storage_agent import CloudStorageManager
        cloud_path = params.get("cloud_path", "")
        local_path = params.get("local_path", "")
        provider = params.get("provider", "s3")
        manager = CloudStorageManager()
        return manager.download_file(cloud_path, local_path, provider)

    def _handle_cloud_sync(self, params: dict) -> dict:
        """Handle storage_cloud_sync"""
        from src.pristmax.agent.storage_agent import CloudStorageManager
        local_path = params.get("local_path", "")
        cloud_prefix = params.get("cloud_prefix", "")
        provider = params.get("provider", "s3")
        manager = CloudStorageManager()
        return manager.sync_to_cloud(local_path, cloud_prefix, provider)

    # ===== 桌面同步处理 =====

    def _handle_sync_save(self, params: dict) -> dict:
        """Handle storage_sync_save"""
        from src.pristmax.agent.storage_agent import DesktopSyncManager
        path = params.get("path", "")
        scan_result = params.get("scan_result", {})
        manager = DesktopSyncManager()
        return manager.save_scan_result(path, scan_result)

    def _handle_sync_list(self, params: dict) -> dict:
        """Handle storage_sync_list"""
        from src.pristmax.agent.storage_agent import DesktopSyncManager
        manager = DesktopSyncManager()
        return {"paths": manager.list_synced_paths()}

    def _handle_sync_to_cloud(self, params: dict) -> dict:
        """Handle storage_sync_to_cloud"""
        from src.pristmax.agent.storage_agent import DesktopSyncManager
        provider = params.get("provider", "s3")
        manager = DesktopSyncManager()
        return manager.sync_to_cloud(provider=provider)

    def _handle_sync_from_cloud(self, params: dict) -> dict:
        """Handle storage_sync_from_cloud"""
        from src.pristmax.agent.storage_agent import DesktopSyncManager
        provider = params.get("provider", "s3")
        manager = DesktopSyncManager()
        return manager.restore_from_cloud(provider=provider)

    def _handle_health(self, params: dict) -> dict:
        """Handle storage_health"""
        return self.agent.health_check()

    def _handle_cache_stats(self, params: dict) -> dict:
        """Handle storage_cache_stats"""
        return self.agent.get_cache_stats()

    def _handle_history(self, params: dict) -> dict:
        """Handle storage_history"""
        limit = params.get("limit", 20)
        return {"history": self.agent.get_scan_history(limit)}

    def _handle_clear_expired(self, params: dict) -> dict:
        """Handle storage_clear_expired"""
        deleted = self.agent.clear_expired_cache()
        return {"deleted": deleted}

    # ===== MCP 协议处理 =====

    def handle_request(self, request: dict) -> str:
        """Handle incoming MCP request"""
        method = request.get("method", "")
        params = request.get("params", {})
        id = request.get("id")

        # MCP Protocol Methods
        if method == "initialize":
            return self.protocol.response(id, {
                "protocolVersion": MCP_VERSION,
                "serverInfo": {
                    "name": "storage-agent",
                    "version": "2.0.0"
                },
                "capabilities": {
                    "tools": {},
                    "security": {
                        "readonly_mode": _security_config.readonly_mode,
                        "approval_required": _security_config.require_approval
                    }
                }
            })

        elif method == "tools/list":
            return self.protocol.response(id, {
                "tools": self.get_tools_list()
            })

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})

            if tool_name in self._tool_handlers:
                try:
                    result = self._tool_handlers[tool_name](tool_args)
                    return self.protocol.response(id, {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2, ensure_ascii=False)
                            }
                        ]
                    })
                except Exception as e:
                    return self.protocol.error(id, -32603, f"Tool execution failed: {str(e)}")
            else:
                return self.protocol.error(id, -32602, f"Unknown tool: {tool_name}")

        elif method == "shutdown":
            return self.protocol.response(id, None)

        else:
            return self.protocol.error(id, -32601, f"Method not found: {method}")

    def run_stdio(self):
        """Run MCP server over stdio (for Claude Code integration)"""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                request = self.protocol.parse_request(line)
                response = self.handle_request(request)
                print(response, flush=True)

            except KeyboardInterrupt:
                break
            except Exception as e:
                error_response = self.protocol.error(None, -32603, str(e))
                print(error_response, flush=True)

        self.agent.close()

    def run_server(self, port: int = 5003):
        """Run MCP server over HTTP (alternative mode)"""
        from flask import Flask, request, jsonify

        app = Flask(__name__)

        @app.route("/mcp", methods=["POST"])
        def mcp_endpoint():
            request_data = request.get_json()
            response = self.handle_request(request_data)
            return jsonify(json.loads(response))

        @app.route("/tools", methods=["GET"])
        def list_tools():
            return jsonify({"tools": self.get_tools_list()})

        @app.route("/security/status", methods=["GET"])
        def security_status():
            return jsonify(self._handle_security_status({}))

        @app.route("/security/config", methods=["POST"])
        def security_config():
            data = request.get_json()
            return jsonify(self._handle_security_config(data))

        @app.route("/approvals", methods=["GET"])
        def list_approvals():
            status = request.args.get("status")
            return jsonify(self._handle_approval_query({"status": status or "pending"}))

        @app.route("/approvals/<operation_id>/<action>", methods=["POST"])
        def approval_action(operation_id, action):
            return jsonify(self._handle_approval_action({
                "operation_id": operation_id,
                "action": action
            }))

        print(f"🚀 Storage Agent MCP Server running on http://localhost:{port}/mcp")
        print(f"   Tools available: {len(self.get_tools_list())}")
        print(f"   Security: readonly={_security_config.readonly_mode}, approval={_security_config.require_approval}")
        app.run(host="0.0.0.0", port=port, debug=False)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Storage Agent MCP Server (安全增强版)")
    parser.add_argument("--port", type=int, default=5003, help="HTTP server port (default: 5003)")
    parser.add_argument("--mode", choices=["stdio", "http"], default="stdio",
                        help="Server mode: stdio (for Claude Code) or http (for API access)")
    parser.add_argument("--db", help="Database path (default: :memory:)")

    # 安全配置参数
    parser.add_argument("--allowed-paths", help="允许访问的路径（逗号分隔）")
    parser.add_argument("--readonly", action="store_true", default=True, help="只读模式（默认开启）")
    parser.add_argument("--no-readonly", action="store_true", help="禁用只读模式")
    parser.add_argument("--require-approval", action="store_true", default=True, help="需要审批（默认开启）")
    parser.add_argument("--no-approval", action="store_true", help="禁用审批")
    parser.add_argument("--max-files", type=int, default=1000000, help="最大扫描文件数")
    parser.add_argument("--max-size-gb", type=int, default=10000, help="最大扫描大小(GB)")

    args = parser.parse_args()

    # 应用安全配置
    if args.allowed_paths:
        _security_config.allowed_paths = args.allowed_paths.split(',')
    if args.no_readonly:
        _security_config.readonly_mode = False
    if args.no_approval:
        _security_config.require_approval = False
    _security_config.max_scan_files = args.max_files
    _security_config.max_scan_size_gb = args.max_size_gb

    server = StorageAgentMCPServer(db_path=args.db or ":memory:")

    if args.mode == "stdio":
        print("🚀 Storage Agent MCP Server ready (stdio mode)", flush=True)
        print(f"   Security: readonly={_security_config.readonly_mode}, approval={_security_config.require_approval}", flush=True)
        server.run_stdio()
    else:
        server.run_server(port=args.port)


if __name__ == "__main__":
    main()
