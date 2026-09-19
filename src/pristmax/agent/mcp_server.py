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
                        "limit": {"type": "integer", "description": "返回数量", "default": 20}
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
                        "max_size_gb": {"type": "integer", "description": "最大扫描大小(GB)"}
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
        files = self.agent.analyze_large_files(path, min_size_mb=min_mb, limit=limit)
        return {
            "files": [{"path": f.path, "size": f.size, "size_display": f.size_display} for f in files],
            "count": len(files)
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
        return {"stats": stats, "suggestions": suggestions}

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
        else:
            result = self.agent.cleanup_large_files(path, min_size_mb=min_size_mb, dry_run=True, auto_approve=True)

        # 确保是预览模式
        result['dry_run'] = True
        result['warning'] = '这是预览模式，实际删除需要审批'
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

        return {
            "success": True,
            "config": {
                "allowed_paths": _security_config.allowed_paths,
                "readonly_mode": _security_config.readonly_mode,
                "require_approval": _security_config.require_approval,
                "max_scan_files": _security_config.max_scan_files,
                "max_scan_size_gb": _security_config.max_scan_size_gb
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
