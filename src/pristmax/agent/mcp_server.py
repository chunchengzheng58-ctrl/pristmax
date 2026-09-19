"""
Storage Agent MCP Server

MCP (Model Context Protocol) Server for Storage Agent.
Allows AI assistants (Claude Code, Cursor, etc.) to use Storage Agent tools.

Usage:
    # As standalone server
    python -m src.pristmax.agent.mcp_server

    # Or integrate with Claude Code via:
    # claude_desktop_config.json
"""

import json
import sys
import io
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.pristmax.agent.storage_agent import StorageAgent

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
    """Storage Agent MCP Server"""

    def __init__(self, db_path: str = ":memory:"):
        self.agent = StorageAgent(db_path=db_path)
        self.protocol = MCPProtocol()
        self._tool_handlers = self._register_tools()

    def _register_tools(self) -> dict:
        """Register available tools"""
        return {
            "storage_stats": self._handle_stats,
            "storage_large_files": self._handle_large_files,
            "storage_duplicates": self._handle_duplicates,
            "storage_suggestions": self._handle_suggestions,
            "storage_analyze": self._handle_analyze,
            "storage_chat": self._handle_chat,
            "storage_cleanup_duplicates": self._handle_cleanup_duplicates,
            "storage_cleanup_large": self._handle_cleanup_large,
        }

    def get_tools_list(self) -> list:
        """Return list of available tools for MCP"""
        return [
            {
                "name": "storage_stats",
                "description": "Get storage statistics for a directory including total files, size, and category distribution",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to analyze"},
                        "incremental": {"type": "boolean", "description": "Use incremental scan (default: true)", "default": True}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_large_files",
                "description": "Find large files in a directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to analyze"},
                        "min_size_mb": {"type": "integer", "description": "Minimum file size in MB (default: 100)", "default": 100},
                        "limit": {"type": "integer", "description": "Maximum number of files to return (default: 20)", "default": 20}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_duplicates",
                "description": "Find duplicate files in a directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to analyze"},
                        "min_size_kb": {"type": "integer", "description": "Minimum file size in KB (default: 1)", "default": 1}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_suggestions",
                "description": "Get intelligent storage optimization suggestions",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to analyze"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_analyze",
                "description": "Comprehensive storage analysis with category breakdown",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to analyze"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_chat",
                "description": "Natural language storage assistant - ask questions about storage in plain English",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to analyze"},
                        "question": {"type": "string", "description": "Question in natural language"}
                    },
                    "required": ["path", "question"]
                }
            },
            {
                "name": "storage_cleanup_duplicates",
                "description": "Preview duplicate file cleanup (dry-run mode)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to analyze"},
                        "execute": {"type": "boolean", "description": "Execute cleanup (default: false, just preview)", "default": False}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "storage_cleanup_large",
                "description": "Preview large file cleanup (dry-run mode)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to analyze"},
                        "min_size_mb": {"type": "integer", "description": "Minimum file size in MB (default: 100)", "default": 100},
                        "execute": {"type": "boolean", "description": "Execute cleanup (default: false, just preview)", "default": False}
                    },
                    "required": ["path"]
                }
            },
        ]

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

    def _handle_cleanup_duplicates(self, params: dict) -> dict:
        """Handle storage_cleanup_duplicates tool call"""
        path = params.get("path", ".")
        execute = params.get("execute", False)
        result = self.agent.cleanup_duplicates(path, dry_run=not execute)
        return result

    def _handle_cleanup_large(self, params: dict) -> dict:
        """Handle storage_cleanup_large tool call"""
        path = params.get("path", ".")
        min_mb = params.get("min_size_mb", 100)
        execute = params.get("execute", False)
        result = self.agent.cleanup_large_files(path, min_size_mb=min_mb, dry_run=not execute)
        return result

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
                    "version": "1.0.0"
                },
                "capabilities": {
                    "tools": {}
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

        print(f"🚀 Storage Agent MCP Server running on http://localhost:{port}/mcp")
        print(f"   Tools available: {len(self.get_tools_list())}")
        app.run(host="0.0.0.0", port=port, debug=False)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Storage Agent MCP Server")
    parser.add_argument("--port", type=int, default=5003, help="HTTP server port (default: 5003)")
    parser.add_argument("--mode", choices=["stdio", "http"], default="stdio",
                        help="Server mode: stdio (for Claude Code) or http (for API access)")
    parser.add_argument("--db", help="Database path (default: :memory:)")

    args = parser.parse_args()

    server = StorageAgentMCPServer(db_path=args.db or ":memory:")

    if args.mode == "stdio":
        print("🚀 Storage Agent MCP Server ready (stdio mode)", flush=True)
        server.run_stdio()
    else:
        server.run_server(port=args.port)


if __name__ == "__main__":
    main()
