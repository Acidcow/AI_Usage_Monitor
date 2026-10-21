from typing import Dict, Any, List, Optional

class NodeRegistry:
    """
    Manages registered and discovered remote AI compute nodes and persistent device inventory.
    Backed by persistent SQLite storage in UsageDatabase.
    """

    def __init__(self, database):
        self.db = database

    def register_node(
        self,
        name: str,
        endpoint: str,
        engine: str = "ollama",
        max_concurrency: int = 1,
        queue_timeout_seconds: float = 30.0,
        priority: int = 5,
        models: Optional[List[Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        node_id: Optional[str] = None,
        is_trusted: int = 1,
        compute_group: str = "Active Compute"
    ) -> Dict[str, Any]:
        """Registers a remote AI instance into the managed pool."""
        return self.db.register_managed_node(
            name=name,
            endpoint=endpoint,
            engine=engine,
            max_concurrency=max_concurrency,
            queue_timeout_seconds=queue_timeout_seconds,
            priority=priority,
            models=models,
            metadata=metadata,
            node_id=node_id,
            is_trusted=is_trusted,
            compute_group=compute_group
        )

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a managed node by its unique ID."""
        return self.db.get_managed_node(node_id)

    def list_nodes(
        self,
        status: Optional[str] = None,
        engine: Optional[str] = None,
        compute_group: Optional[str] = None,
        is_trusted: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Lists registered nodes with optional status, engine, group, or trust filtering."""
        nodes = self.db.list_managed_nodes(status=status, engine=engine)
        if compute_group is not None:
            nodes = [n for n in nodes if n.get("compute_group", "Active Compute") == compute_group]
        if is_trusted is not None:
            nodes = [n for n in nodes if n.get("is_trusted", 1) == is_trusted]
        return nodes

    def update_node(self, node_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Updates configuration for a managed node."""
        return self.db.update_managed_node(node_id, **kwargs)

    def update_node_status(self, node_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Updates runtime health status ('ONLINE', 'BUSY', 'UNHEALTHY', 'OFFLINE')."""
        return self.db.update_managed_node(node_id, status=status)

    def delete_node(self, node_id: str) -> bool:
        """Deletes a node from the registry."""
        return self.db.delete_managed_node(node_id)

    # Device Inventory operations
    def upsert_device(self, alias: str, ip: str, **kwargs) -> Dict[str, Any]:
        return self.db.upsert_device_inventory(alias=alias, ip=ip, **kwargs)

    def get_device(self, alias_or_ip: str) -> Optional[Dict[str, Any]]:
        return self.db.get_device_inventory(alias_or_ip)

    def list_devices(self, state: Optional[str] = None, compute_group: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.db.list_device_inventory(state=state, compute_group=compute_group)

    def delete_device(self, alias: str) -> bool:
        return self.db.delete_device_inventory(alias)

    def format_compact_node_card(self, node: dict) -> dict:
        """
        Formats a node record into compact display metadata featuring prominent Alias/IP headers,
        service/platform badges, and clean model chip lists.
        """
        name = node.get("name") or "Remote Node"
        endpoint = node.get("endpoint") or ""
        engine = (node.get("engine") or "ollama").lower()

        engine_labels = {
            "ollama": "🦙 Ollama",
            "lmstudio": "🤖 LM Studio",
            "vllm": "⚡ vLLM / LocalAI",
            "oobabooga": "📜 Text Gen WebUI",
            "tabby_kobold": "🐱 Tabby / Kobold",
            "open_webui": "🌐 Open WebUI"
        }
        engine_label = engine_labels.get(engine, f"⚡ {engine.title()}")

        raw_models = node.get("models") or []
        formatted_models = []
        for m in raw_models:
            if isinstance(m, dict):
                m_name = m.get("name", "model")
                m_size = m.get("size", "")
                m_param = m.get("parameter_size", "")
                formatted_models.append({
                    "name": m_name,
                    "size": m_size,
                    "parameter_size": m_param,
                    "badge": f"{m_name} ({m_param or m_size})".strip() if (m_param or m_size) else m_name
                })
            else:
                formatted_models.append({
                    "name": str(m),
                    "size": "",
                    "parameter_size": "",
                    "badge": str(m)
                })

        clean_ep = endpoint.replace("http://", "").replace("https://", "").split("/")[0]
        ep_ip = clean_ep.split(":")[0] if ":" in clean_ep else clean_ep
        if endpoint and endpoint not in name and ep_ip not in name:
            header_title = f"{name} ({endpoint})"
        else:
            header_title = name

        return {
            "node_id": node.get("id"),
            "header_title": header_title,
            "engine": engine,
            "engine_label": engine_label,
            "endpoint": endpoint,
            "models": formatted_models,
            "model_count": len(formatted_models),
            "status": node.get("status", "ONLINE"),
            "is_trusted": node.get("is_trusted", 1),
            "compute_group": node.get("compute_group", "Active Compute"),
            "priority": node.get("priority", 5),
            "max_concurrency": node.get("max_concurrency", 1)
        }

