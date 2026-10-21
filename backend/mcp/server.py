import sys
import json
import logging
from typing import Dict, Any, Optional

class MCPServer:
    """
    Model Context Protocol (MCP) Server implementing JSON-RPC 2.0.
    Exposes LAN AI node discovery, multi-node managed pool controls, and
    governed completions directly to autonomous agents (Claude Code, Cursor, Windsurf, etc.).
    """

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "ai-usage-monitor-proxy"
    SERVER_VERSION = "0.1.0"

    def __init__(self, scanner=None, registry=None, governor=None):
        self.scanner = scanner
        self.registry = registry
        self.governor = governor

    def get_tool_definitions(self) -> list:
        return [
            {
                "name": "scan_lan_ai_services",
                "description": "Scans the local area network (LAN) for exposed Ollama, LM Studio, and vLLM AI services.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "subnet": {"type": "string", "description": "Optional CIDR prefix (e.g. 192.168.1.0/24)"},
                        "targets": {"type": "array", "items": {"type": "string"}, "description": "Optional list of host:port targets to probe"},
                        "timeout": {"type": "number", "description": "Connection timeout in seconds (default: 0.25)"}
                    }
                }
            },
            {
                "name": "list_managed_nodes",
                "description": "Lists all registered remote AI compute nodes, active models, health, and queue depth.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "Filter by status: ONLINE, BUSY, UNHEALTHY, OFFLINE"},
                        "engine": {"type": "string", "description": "Filter by engine: ollama, lmstudio, vllm, openai_compatible"}
                    }
                }
            },
            {
                "name": "register_managed_node",
                "description": "Registers an AI instance into the managed pool with concurrency ceilings to prevent overwhelming the machine.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "User-friendly name of the node"},
                        "endpoint": {"type": "string", "description": "Base URL of the node (e.g. http://192.168.1.45:11434)"},
                        "engine": {"type": "string", "description": "Engine type: ollama, lmstudio, vllm, openai_compatible (default: ollama)"},
                        "max_concurrency": {"type": "integer", "description": "Max concurrent active requests (default: 1)"},
                        "queue_timeout_seconds": {"type": "number", "description": "Max queue wait time before timeout shedding (default: 30.0)"},
                        "priority": {"type": "integer", "description": "Scheduling priority (default: 5)"}
                    },
                    "required": ["name", "endpoint"]
                }
            },
            {
                "name": "generate_completion",
                "description": "Executes an inference completion on a managed node through the traffic governor with queue protection and token logging.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string", "description": "Target managed node ID"},
                        "model": {"type": "string", "description": "Model name to query"},
                        "prompt": {"type": "string", "description": "Prompt text for the model"},
                        "stream": {"type": "boolean", "description": "Whether to stream (default: false)"}
                    },
                    "required": ["node_id", "model", "prompt"]
                }
            },
            {
                "name": "get_traffic_telemetry",
                "description": "Retrieves live active requests, queue depth, and routed token counts for a node or the entire cluster.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string", "description": "Optional node ID to filter stats"}
                    }
                }
            }
        ]

    def handle_json_rpc(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Processes a single JSON-RPC 2.0 MCP request dict and returns response dict."""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {}) or {}

        # 1. initialize
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": self.SERVER_NAME,
                        "version": self.SERVER_VERSION
                    }
                }
            }

        # 2. notifications/initialized & ping
        if method in ["notifications/initialized", "initialized"]:
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # 3. tools/list
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self.get_tool_definitions()
                }
            }

        # 4. tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {}) or {}
            try:
                res_data = self._execute_tool(tool_name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(res_data, indent=2)
                            }
                        ],
                        "isError": False
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"error": str(e)})
                            }
                        ],
                        "isError": True
                    }
                }

        # Unknown Method
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method '{method}' not found."
            }
        }

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name == "scan_lan_ai_services":
            if not self.scanner:
                return {"error": "LANScanner not configured on server"}
            targets = args.get("targets")
            timeout = args.get("timeout")
            subnet = args.get("subnet")

            if targets:
                return self.scanner.scan_targets(targets, timeout=timeout)
            return self.scanner.scan_local_subnet(subnet_cidr=subnet, timeout=timeout)

        if name == "list_managed_nodes":
            if not self.registry:
                return []
            return self.registry.list_nodes(status=args.get("status"), engine=args.get("engine"))

        if name == "register_managed_node":
            if not self.registry:
                return {"error": "NodeRegistry not configured"}
            return self.registry.register_node(
                name=args["name"],
                endpoint=args["endpoint"],
                engine=args.get("engine", "ollama"),
                max_concurrency=args.get("max_concurrency", 1),
                queue_timeout_seconds=args.get("queue_timeout_seconds", 30.0),
                priority=args.get("priority", 5)
            )

        if name == "generate_completion":
            if not self.governor:
                return {"error": "TrafficGovernor not configured"}
            return self.governor.forward_completion(
                node_id=args["node_id"],
                model=args["model"],
                prompt=args["prompt"],
                stream=args.get("stream", False)
            )

        if name == "get_traffic_telemetry":
            if not self.governor:
                return {}
            return self.governor.get_telemetry(node_id=args.get("node_id"))

        raise ValueError(f"Unknown tool '{name}'")

    def run_stdio(self):
        """Runs the MCP server over standard input/output for CLI/IDE agents."""
        for line in sys.stdin:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                req = json.loads(line_str)
                resp = self.handle_json_rpc(req)
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"}
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

if __name__ == "__main__":
    from backend.storage.database import UsageDatabase
    from backend.discovery.lan_scanner import LANScanner
    from backend.discovery.node_registry import NodeRegistry
    from backend.discovery.traffic_governor import TrafficGovernor

    db = UsageDatabase()
    scanner = LANScanner()
    registry = NodeRegistry(db)
    governor = TrafficGovernor(registry, db)
    server = MCPServer(scanner=scanner, registry=registry, governor=governor)
    server.run_stdio()
