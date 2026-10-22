"""
Canonical Unified Telemetry Taxonomy & Cross-Platform Terminology Mapping (AIUM-904).

Provides a single, deterministic 8-tier taxonomy that normalizes disparate provider concepts
(Organizations, Accounts, Tenants, Teams, Workspaces, Compute Pools, Seats, Named Tokens,
Local vs. Remote LAN Compute Nodes, Client Workstations, Access Routes, Models, and Sessions)
into a unified structure across all backend APIs, charts, mini widgets, and reports.
"""

import os
from typing import Dict, Any, Optional, List, Tuple


LOCAL_HOST_IDENTIFIERS = {
    "127.0.0.1",
    "localhost",
    "::1",
    "0.0.0.0",
    "local",
    "local-default",
    "local workstation",
}


def get_local_machine_names() -> set:
    names = set(LOCAL_HOST_IDENTIFIERS)
    for env_key in ("COMPUTERNAME", "HOSTNAME"):
        val = os.environ.get(env_key)
        if val:
            names.add(val.strip().lower())
    return names


CANONICAL_TAXONOMY_TIERS: List[Dict[str, Any]] = [
    {
        "tier": "L1",
        "code": "platform",
        "key": "platform",
        "db_column": "provider",
        "label": "Platform / Provider",
        "short_label": "Platform",
        "description": "Primary AI platform, vendor, or inference engine family.",
        "examples": ["Claude (Anthropic)", "Google Gemini", "Ollama (Compute)", "ChatGPT / OpenAI", "M365 Copilot"],
    },
    {
        "tier": "L2",
        "code": "tenant_account",
        "key": "tenant_account",
        "db_column": "account_id",
        "label": "Tenant / Account Umbrella",
        "short_label": "Tenant / Account",
        "description": "Billing account, personal subscription (e.g. Claude Pro), or enterprise organization tenant.",
        "examples": ["Claude Pro (Personal)", "Synthesis2 (Org)", "acidcow@gmail.com", "Local Hardware Estate"],
    },
    {
        "tier": "L3",
        "code": "workspace_pool",
        "key": "workspace_pool",
        "db_column": "team_name",
        "label": "Workspace / Quota Pool",
        "short_label": "Workspace / Pool",
        "description": "Allocation pool, subscription tier, team workspace, department/BU, or compute node group.",
        "examples": ["Claude Pro", "Team Workspace Pool (Synthesis2)", "Active Compute Pool", "GCP AI Studio Project"],
    },
    {
        "tier": "L4",
        "code": "principal_seat",
        "key": "principal_seat",
        "db_column": "user_name",
        "label": "Principal / Seat / Credential",
        "short_label": "Principal / Seat",
        "description": "Authenticated user seat, developer operator, API key, or named token consuming the quota.",
        "examples": ["James Eckhardt", "tok_gem_flash", "tok_gem_pro", "Service Principal"],
    },
    {
        "tier": "L5",
        "code": "compute_node",
        "key": "compute_node",
        "db_column": "instance_id",
        "label": "Compute Node & Locality",
        "short_label": "Compute Node",
        "description": "Execution runtime instance classified by Locality: Local Node (this machine), Remote LAN Node, or Cloud API.",
        "examples": ["Local: DESKTOP-C9FNLB9 (127.0.0.1)", "Remote LAN: JamesE-PC (10.1.7.74)", "Cloud: Anthropic API"],
    },
    {
        "tier": "L6",
        "code": "client_host",
        "key": "client_host",
        "db_column": "client_ip",
        "label": "Originating Client / Workstation",
        "short_label": "Client Host",
        "description": "Originating workstation alias and IP address initiating the AI request.",
        "examples": ["DESKTOP-C9FNLB9 (127.0.0.1)", "JamesE-PC (10.1.7.74)"],
    },
    {
        "tier": "L7",
        "code": "access_route",
        "key": "access_route",
        "db_column": "source",
        "label": "Traffic / Access Route",
        "short_label": "Access Route",
        "description": "Ingestion and routing channel through which telemetry was captured.",
        "examples": ["direct (Upstream API)", "proxy (Port 8766)", "emulator (Ollama Bridge :8989)", "cli_scanner / log_scanner"],
    },
    {
        "tier": "L8",
        "code": "model_session",
        "key": "model_session",
        "db_column": "model",
        "label": "Model & Session Context",
        "short_label": "Model & Session",
        "description": "Specific LLM weight/version and conversation or execution session identifier.",
        "examples": ["claude-sonnet-4-6", "gemini-2.5-pro", "gemma4:e4b", "nomic-embed-text:latest"],
    },
]


PROVIDER_TERMINOLOGY_MATRIX: Dict[str, Dict[str, str]] = {
    "claude": {
        "platform": "Anthropic Claude",
        "tenant_account": "Personal Account (Claude Pro / Max) or Organization (Enterprise / Team)",
        "workspace_pool": "Subscription Quota Pool (Personal 5h/Weekly vs. Team Shared Workspace / Dept)",
        "principal_seat": "Member Seat / OAuth User / Anthropic API Key",
        "compute_node": "Anthropic Cloud Runtime / Local Claude Code CLI Host",
        "client_host": "Developer Workstation / IDE Host Alias & IP",
        "access_route": "Direct API, Transparent Proxy (:8766), or Local CLI JSONL Scanner",
        "model_session": "Claude Model (Opus / Sonnet / Haiku) & Session / Message UUID",
    },
    "gemini": {
        "platform": "Google Gemini / AI Studio",
        "tenant_account": "Google Account Umbrella / Cloud Organization",
        "workspace_pool": "Google Cloud / AI Studio Project Quota Pool",
        "principal_seat": "Named AI Studio API Key (tok_gem_*) or OAuth 2.0 Bearer Seat",
        "compute_node": "Google Generative Language Cloud Endpoint",
        "client_host": "Originating Workstation / Agent Host Alias & IP",
        "access_route": "Direct REST/gRPC, Transparent Proxy (:8766), or OAuth Loopback",
        "model_session": "Gemini Model (2.5 Pro / 2.0 Flash) & Session ID",
    },
    "ollama": {
        "platform": "Ollama / Local & LAN Compute",
        "tenant_account": "On-Premise Hardware Estate / Cluster Owner",
        "workspace_pool": "Compute Pool Group (Local Host vs. Active Compute LAN Pool)",
        "principal_seat": "Calling Operator / Agent / Workstation User",
        "compute_node": "Physical GPU/CPU Host Node — Local (127.0.0.1) vs. Remote LAN Node (e.g. 10.1.7.74)",
        "client_host": "Requesting Client Machine Alias & IP",
        "access_route": "Direct (:11434), Governed Proxy / Emulator (:8989), or Server Log Scanner",
        "model_session": "GGUF Model Tag (gemma4, qwen3.5, nomic-embed) & Inference Run ID",
    },
    "chatgpt": {
        "platform": "OpenAI / ChatGPT",
        "tenant_account": "OpenAI Organization / Personal Plus-Pro Account",
        "workspace_pool": "OpenAI Project / Tier Rate-Limit Pool",
        "principal_seat": "OpenAI Project API Key / User Seat",
        "compute_node": "OpenAI Cloud Inference Endpoint",
        "client_host": "Originating Workstation Alias & IP",
        "access_route": "Direct OpenAI v1 API or Transparent Proxy (:8766)",
        "model_session": "OpenAI Model (GPT-4o / o3-mini) & Request/Session ID",
    },
    "copilot": {
        "platform": "Microsoft 365 Copilot",
        "tenant_account": "Microsoft Entra ID Tenant",
        "workspace_pool": "Enterprise E5 / Department License Pool",
        "principal_seat": "Assigned Entra User Principal Name (UPN) Seat",
        "compute_node": "Microsoft 365 Graph Cloud",
        "client_host": "Managed Corporate Endpoint / Workstation",
        "access_route": "M365 Graph API / Telemetry Importer",
        "model_session": "Copilot Assistant Model & Interactive Session",
    },
}


def _resolve_node_locality_details(
    provider: Optional[str] = None,
    instance_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    node_endpoint: Optional[str] = None,
    client_ip: Optional[str] = None,
    session_id: Optional[str] = None,
    nodes_map: Optional[Dict[str, Dict[str, Any]]] = None,
    managed_nodes_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, str]:
    prov = (provider or "").strip().lower()
    inst = (instance_id or "local").strip()
    ep = (endpoint or node_endpoint or "").strip().lower()
    sess = (session_id or "").strip()
    local_names = get_local_machine_names()
    machine_name = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "Local Workstation"

    # Resolve node from session_id if session_id encodes remote_node_ollama_... or stream_node_ollama_...
    if inst in ("local", "local-default", "") and (sess.startswith("remote_node_") or sess.startswith("stream_node_")):
        prefix_stripped = sess.replace("remote_", "", 1).replace("stream_", "", 1)
        parts = prefix_stripped.rsplit("_", 1)
        if parts[0].startswith("node_"):
            inst = parts[0]

    nmap = nodes_map if nodes_map is not None else (managed_nodes_map or {})
    node_info = nmap.get(inst)
    if node_info:
        ep = (node_info.get("endpoint") or ep).strip().lower()
        node_name = node_info.get("name") or inst
    else:
        node_name = inst

    is_local_provider = prov in ("ollama", "lmstudio", "vllm", "oobabooga", "tabby_kobold", "local")

    if is_local_provider or inst.startswith("node_"):
        ep_host = ""
        if ep:
            clean_ep = ep.replace("http://", "").replace("https://", "").split("/")[0]
            ep_host = clean_ep.split(":")[0].strip().lower()

        if ep_host and ep_host not in local_names:
            display = f"{node_name} ({ep_host})" if ep_host not in node_name.lower() else node_name
            return {
                "locality": "remote_lan",
                "locality_label": "Remote LAN Node",
                "node_id": inst,
                "node_display_name": display,
            }

        if inst.lower() not in local_names and not inst.startswith("node_"):
            return {
                "locality": "remote_lan",
                "locality_label": "Remote LAN Node",
                "node_id": inst,
                "node_display_name": node_name,
            }

        if node_info and node_name.strip().lower() not in local_names and ep_host and ep_host not in local_names:
            display = f"{node_name} ({ep_host})"
            return {
                "locality": "remote_lan",
                "locality_label": "Remote LAN Node",
                "node_id": inst,
                "node_display_name": display,
            }

        local_disp = node_name if (node_info and node_name != inst) else f"Local Node ({machine_name})"
        return {
            "locality": "local",
            "locality_label": "Local Node (This PC)",
            "node_id": inst if inst not in ("", "local-default") else "local",
            "node_display_name": local_disp,
        }

    return {
        "locality": "cloud",
        "locality_label": "Cloud API",
        "node_id": inst or "cloud",
        "node_display_name": f"{prov.capitalize()} Cloud API" if prov else "Cloud API",
    }


def classify_node_locality(
    provider: Optional[str] = None,
    instance_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    node_endpoint: Optional[str] = None,
    client_ip: Optional[str] = None,
    session_id: Optional[str] = None,
    nodes_map: Optional[Dict[str, Dict[str, Any]]] = None,
    managed_nodes_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    """
    Returns (locality_code, locality_label):
      - ('local', 'Local Node (This PC)')
      - ('remote_lan', 'Remote LAN Node')
      - ('cloud', 'Cloud API')
    """
    info = _resolve_node_locality_details(
        provider=provider,
        instance_id=instance_id,
        endpoint=endpoint,
        node_endpoint=node_endpoint,
        client_ip=client_ip,
        session_id=session_id,
        nodes_map=nodes_map,
        managed_nodes_map=managed_nodes_map,
    )
    return info["locality"], info["locality_label"]


def classify_account_tier(
    provider: Optional[str] = None,
    account_id: Optional[str] = None,
    team_name: Optional[str] = None,
    plan_type: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Returns (account_tier_code, account_tier_label) distinguishing Personal Pro vs. Team/Enterprise Pool:
      - ('personal_pro', 'Claude Pro (Personal)')
      - ('team_org', 'Team / Enterprise Pool (Synthesis2)')
      - ('on_prem_compute', 'On-Premise Compute')
    """
    prov = (provider or "").strip().lower()
    acct = (account_id or "").strip()
    team = (team_name or "").strip()
    plan = (plan_type or "").strip()

    if prov in ("ollama", "lmstudio", "vllm", "local"):
        return "on_prem_compute", "On-Premise Compute"

    is_company_team = False
    team_lower = team.lower()
    acct_lower = acct.lower()
    if acct_lower in ("synthesis2", "synthesis", "synthesis engineering core") or team_lower in (
        "synthesis2",
        "synthesis",
        "synthesis engineering core",
    ):
        if "pro" not in team_lower and "pro" not in acct_lower:
            is_company_team = True

    if prov == "claude":
        if is_company_team:
            pool_name = team or acct or "Synthesis2"
            return "team_org", f"Team / Enterprise Pool ({pool_name})"
        return "personal_pro", "Claude Pro (Personal)"

    if prov == "gemini":
        return "personal_pro", f"Google Account ({acct or 'acidcow@gmail.com'})"

    if is_company_team:
        return "team_org", f"Team Pool ({team or acct})"
    return "personal_pro", plan or f"{prov.capitalize()} Personal"


def normalize_event_taxonomy(
    row: Dict[str, Any],
    nodes_map: Optional[Dict[str, Dict[str, Any]]] = None,
    managed_nodes_map: Optional[Dict[str, Dict[str, Any]]] = None,
    active_plan_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Enriches a raw usage_events record or aggregated report row with all 8 canonical taxonomy fields.
    """
    prov = (row.get("provider") or "unknown").lower()
    inst = row.get("instance_id") or "local"
    cip = row.get("client_ip") or "127.0.0.1"
    calias = row.get("client_alias") or ""
    sess = row.get("session_id") or ""
    acct = row.get("account_id") or ""
    team = row.get("team_name") or ""
    user = row.get("user_name") or os.environ.get("USERNAME") or "James Eckhardt"
    source = row.get("source") or "direct"
    model = row.get("model") or "default"
    plan_type = (active_plan_map or {}).get(prov, "")

    nmap = nodes_map if nodes_map is not None else (managed_nodes_map or {})
    loc_info = _resolve_node_locality_details(
        provider=prov,
        instance_id=inst,
        client_ip=cip,
        session_id=sess,
        nodes_map=nmap,
    )
    acct_tier, acct_tier_label = classify_account_tier(
        provider=prov,
        account_id=acct,
        team_name=team,
        plan_type=plan_type,
    )

    if not calias or calias == cip:
        if cip in LOCAL_HOST_IDENTIFIERS:
            calias = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "Local Workstation"
        else:
            calias = cip

    client_host_label = f"{calias} ({cip})" if calias and cip and cip not in calias else (calias or cip)

    route_labels = {
        "direct": "Direct API",
        "proxy": "Transparent Proxy (:8766)",
        "emulator": "Ollama Bridge (:8989)",
        "cli_scanner": "Claude Code Local CLI",
        "local_cli": "Claude Code Local CLI",
        "log_scanner": "Local Server Log Scanner",
    }
    if prov == "ollama" and source == "proxy":
        access_route_label = "Governed LAN Node Bridge (:8989)"
    else:
        access_route_label = route_labels.get(source, source)

    if prov == "claude":
        tenant_acct = acct if (acct and acct.lower() not in ("default", "none")) else user
        workspace_pool = "Synthesis2" if acct_tier == "team_org" else (team if team and team != "Synthesis2" else "Claude Pro")
    elif prov == "ollama":
        tenant_acct = acct if (acct and acct.lower() not in ("default", "none")) else loc_info["node_display_name"]
        workspace_pool = "Local Host Compute" if loc_info["locality"] == "local" else "Remote LAN Compute Pool"
    elif prov == "gemini":
        tenant_acct = acct or "acidcow@gmail.com"
        workspace_pool = team or "Gemini Pro / AI Studio"
    else:
        tenant_acct = acct or user
        workspace_pool = team or "Standard Pool"

    return {
        "platform": prov,
        "tenant_account": tenant_acct,
        "account_tier": acct_tier,
        "account_scope": acct_tier,
        "account_tier_label": acct_tier_label,
        "workspace_pool": workspace_pool,
        "principal_seat": row.get("token_id") or user,
        "compute_node": loc_info["node_display_name"],
        "instance_id": loc_info["node_id"],
        "node_id": loc_info["node_id"],
        "locality": loc_info["locality"],
        "locality_label": loc_info["locality_label"],
        "client_host": client_host_label,
        "client_ip": cip,
        "access_route": source,
        "access_route_label": access_route_label,
        "model": model,
    }


def get_full_taxonomy_specification() -> Dict[str, Any]:
    """Returns the complete canonical taxonomy specification for API consumers and UI rendering."""
    return {
        "version": "1.0.0",
        "tiers": CANONICAL_TAXONOMY_TIERS,
        "provider_matrix": PROVIDER_TERMINOLOGY_MATRIX,
        "disaggregation_modes": [
            {"id": "locality", "label": "Split Local vs. Remote & Pro vs. Team"},
            {"id": "consolidated", "label": "Consolidated by Platform (L1)"},
            {"id": "tenant_account", "label": "Split by Account / Tenant (L2)"},
            {"id": "workspace_pool", "label": "Split by Workspace / Quota Pool (L3)"},
            {"id": "compute_node", "label": "Split by Compute Node / Instance (L5)"},
            {"id": "client_host", "label": "Split by Client Host / Alias (L6)"},
            {"id": "access_route", "label": "Split by Traffic / Access Route (L7)"},
            {"id": "model", "label": "Split by Model Engine (L8)"},
        ],
        "scope_filters": [
            {"id": "all", "label": "All Scopes & Nodes"},
            {"id": "personal_only", "label": "Personal Pro Only (Excl. Team Pool)"},
            {"id": "team_only", "label": "Team / Org Pool Only"},
            {"id": "local_only", "label": "Local Node Only (This PC)"},
            {"id": "remote_only", "label": "Remote LAN Nodes Only"},
        ],
    }
