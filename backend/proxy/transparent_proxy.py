import datetime
import http.server
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.diagnostics.logging_engine import ErrorCategory
from backend.providers.gemini import GeminiProvider


class SSEResult(tuple):
    """Container for parsed SSE stream tokens and upstream response identifier."""

    def __new__(
        cls,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = "",
        external_id: Optional[str] = None,
    ):
        return super().__new__(
            cls,
            (
                int(input_tokens or 0),
                int(output_tokens or 0),
                str(model or ""),
                external_id,
            ),
        )

    @property
    def input_tokens(self) -> int:
        return self[0]

    @property
    def output_tokens(self) -> int:
        return self[1]

    @property
    def model(self) -> str:
        return self[2]

    @property
    def external_id(self) -> Optional[str]:
        return self[3]

    @property
    def id(self) -> Optional[str]:
        return self[3]

    def get(self, key: str, default: Any = None) -> Any:
        m = {
            "input_tokens": self[0],
            "in_tokens": self[0],
            "output_tokens": self[1],
            "out_tokens": self[1],
            "model": self[2],
            "external_id": self[3],
            "id": self[3],
        }
        return m.get(key, default)


def extract_sse_tokens(sse_bytes: Union[bytes, str]) -> SSEResult:
    """
    Parses SSE byte streams or strings from Anthropic, OpenAI, or Gemini upstreams,
    extracting input_tokens, output_tokens, model, and the upstream response external_id.
    """
    if not sse_bytes:
        return SSEResult(0, 0, "", None)

    if isinstance(sse_bytes, bytes):
        text = sse_bytes.decode("utf-8", errors="replace")
    else:
        text = str(sse_bytes)

    in_tokens = 0
    out_tokens = 0
    model = ""
    external_id = None

    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        raw_data = line[5:].strip()
        if raw_data == "[DONE]":
            continue
        try:
            payload = json.loads(raw_data)
        except Exception:
            continue

        if not isinstance(payload, dict):
            continue

        # Top-level or OpenAI / Anthropic response ID
        if not external_id and payload.get("id"):
            external_id = payload.get("id")

        p_type = payload.get("type")
        if p_type == "message_start":
            msg = payload.get("message", {})
            if msg.get("id"):
                external_id = msg.get("id")
            if msg.get("model"):
                model = msg.get("model")
            usage = msg.get("usage", {})
            in_tokens = usage.get("input_tokens", in_tokens)
        elif p_type == "message_delta":
            usage = payload.get("usage", {})
            out_tokens = usage.get("output_tokens", out_tokens)
        elif "usageMetadata" in payload:
            # Gemini SSE format
            u = payload.get("usageMetadata", {})
            in_tokens = u.get("promptTokenCount", in_tokens)
            out_tokens = u.get("candidatesTokenCount", out_tokens)
            if not external_id and payload.get("responseId"):
                external_id = payload.get("responseId")
        elif "usage" in payload and payload.get("usage"):
            # OpenAI / Ollama SSE format
            u = payload.get("usage", {})
            in_tokens = u.get("prompt_tokens", in_tokens)
            out_tokens = u.get("completion_tokens", out_tokens)
        if not model and payload.get("model"):
            model = payload.get("model")

    return SSEResult(in_tokens, out_tokens, model, external_id)


_extract_sse_tokens = extract_sse_tokens


def evaluate_budget_circuit_breaker(
    database: Any, provider: str, session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates proxy spend limits against recorded SQLite usage events.
    Checks proxy_hourly_budget_usd (default 0.0 = unlimited) and proxy_session_budget_usd (default 0.0 = unlimited).
    """
    if not database:
        return {
            "tripped": False,
            "reason": "Database not configured",
            "hourly_spend_usd": 0.0,
            "budget_limit_usd": 0.0,
            "session_spend_usd": 0.0,
        }

    hourly_limit = 0.0
    session_limit = 0.0
    try:
        if hasattr(database, "get_setting"):
            h_val = database.get_setting("proxy_hourly_budget_usd", 0.0)
            s_val = database.get_setting("proxy_session_budget_usd", 0.0)
            hourly_limit = float(h_val or 0.0)
            session_limit = float(s_val or 0.0)
    except Exception:
        pass

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    one_hour_ago_iso = (now_dt - datetime.timedelta(hours=1)).isoformat()
    one_hour_ago_space = (now_dt - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    hourly_spend_usd = 0.0
    session_spend_usd = 0.0

    try:
        conn = database._get_connection() if hasattr(database, "_get_connection") else None
        lock = getattr(database, "_lock", None)

        def _do_query():
            nonlocal hourly_spend_usd, session_spend_usd
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(estimated_cost), 0.0)
                FROM usage_events
                WHERE recorded_at >= ? OR (recorded_at NOT LIKE '%T%' AND recorded_at >= ?)
                """,
                (one_hour_ago_iso, one_hour_ago_space),
            )
            row = cursor.fetchone()
            hourly_spend_usd = float(row[0] if row and row[0] is not None else 0.0)

            if session_id:
                cursor.execute(
                    "SELECT COALESCE(SUM(estimated_cost), 0.0) FROM usage_events WHERE session_id = ?",
                    (str(session_id),),
                )
                s_row = cursor.fetchone()
                session_spend_usd = float(s_row[0] if s_row and s_row[0] is not None else 0.0)
            conn.close()

        if conn:
            if lock:
                with lock:
                    _do_query()
            else:
                _do_query()
    except Exception:
        pass

    tripped = False
    reason = "Within budget limits"
    budget_limit_usd = 0.0

    if hourly_limit > 0.0 and hourly_spend_usd >= hourly_limit:
        tripped = True
        reason = f"Hourly proxy spend limit reached (${hourly_spend_usd:.2f} >= ${hourly_limit:.2f})"
        budget_limit_usd = hourly_limit
    elif session_limit > 0.0 and session_id and session_spend_usd >= session_limit:
        tripped = True
        reason = f"Session proxy spend limit reached (${session_spend_usd:.2f} >= ${session_limit:.2f})"
        budget_limit_usd = session_limit
    else:
        budget_limit_usd = hourly_limit if hourly_limit > 0.0 else session_limit

    return {
        "tripped": tripped,
        "reason": reason,
        "hourly_spend_usd": round(hourly_spend_usd, 4),
        "budget_limit_usd": float(budget_limit_usd),
        "session_spend_usd": round(session_spend_usd, 4),
    }


def evaluate_spillover_target(
    database: Any, provider: str, nodes_provider: Any = None
) -> Optional[Dict[str, Any]]:
    """
    Evaluates cloud-to-LAN failover/spillover when cloud quotas exceed 85% or cloud provider is in error state.
    Routes to an online Ollama/vLLM LAN worker node.
    """
    if not database:
        return None

    # 1. Check if cloud_to_lan_spillover_enabled is enabled in settings
    spillover_enabled = False
    try:
        if hasattr(database, "get_setting"):
            val = database.get_setting("cloud_to_lan_spillover_enabled", False)
            if isinstance(val, str):
                spillover_enabled = val.lower() in ("true", "1", "yes", "enabled")
            else:
                spillover_enabled = bool(val)
    except Exception:
        pass

    if not spillover_enabled:
        return None

    # 2. Check cloud provider's 5h quota used % >= 85.0 or in ERROR / 429 state
    prov = (provider or "").lower().strip()
    snap = None
    try:
        if hasattr(database, "get_latest_provider_snapshot"):
            snap = database.get_latest_provider_snapshot(prov)
        if not snap and hasattr(database, "get_provider_snapshots"):
            snaps = database.get_provider_snapshots()
            if isinstance(snaps, dict):
                snap = snaps.get(prov)
    except Exception:
        pass

    if not snap:
        try:
            conn = database._get_connection() if hasattr(database, "_get_connection") else None
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM provider_snapshots WHERE provider = ?", (prov,))
                r = cursor.fetchone()
                conn.close()
                if r:
                    snap = dict(r)
        except Exception:
            pass

    if not snap:
        return None

    status = str(snap.get("status", "")).upper()
    is_error = status in ("ERROR", "429", "DEGRADED", "BLOCKED", "RATE_LIMITED")

    used_pct = 0.0
    if "session_used_pct" in snap and snap["session_used_pct"] is not None:
        used_pct = float(snap["session_used_pct"])
    elif "session_remaining_pct" in snap and snap["session_remaining_pct"] is not None:
        used_pct = 100.0 - float(snap["session_remaining_pct"])
    elif "used_pct" in snap and snap["used_pct"] is not None:
        used_pct = float(snap["used_pct"])

    if not (used_pct >= 85.0 or is_error):
        return None

    # 3. Query get_managed_nodes() for an ONLINE local/LAN Ollama worker node
    nodes = []
    if nodes_provider and hasattr(nodes_provider, "get_managed_nodes"):
        try:
            nodes = nodes_provider.get_managed_nodes()
        except Exception:
            pass
    if not nodes and hasattr(database, "get_managed_nodes"):
        try:
            nodes = database.get_managed_nodes()
        except Exception:
            pass
    if not nodes and hasattr(database, "list_managed_nodes"):
        try:
            nodes = database.list_managed_nodes()
        except Exception:
            pass
    if not nodes:
        try:
            conn = database._get_connection() if hasattr(database, "_get_connection") else None
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM managed_nodes")
                nodes = [dict(r) for r in cursor.fetchall()]
                conn.close()
        except Exception:
            pass

    for node in nodes:
        n_status = str(node.get("status", "")).upper()
        n_engine = str(node.get("engine", "")).lower()
        n_endpoint = str(node.get("endpoint", ""))
        if n_status == "ONLINE" and (n_engine in ("ollama", "local", "vllm") or "11434" in n_endpoint):
            node_name = node.get("name") or node.get("id") or "ollama-lan-node"
            endpoint = node.get("endpoint") or "http://127.0.0.1:11434"
            model = "llama3:8b"
            models_json = node.get("models_json")
            if models_json:
                try:
                    m_list = json.loads(models_json) if isinstance(models_json, str) else models_json
                    if isinstance(m_list, list) and len(m_list) > 0:
                        model = str(m_list[0])
                except Exception:
                    pass
            elif node.get("model"):
                model = str(node["model"])

            return {
                "spillover_active": True,
                "target_node": node_name,
                "target_endpoint": endpoint,
                "target_model": model,
            }

    return None


class TransparentProxyHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP Request Handler that transparently proxies LLM calls and extracts token telemetry.
    Supports Anthropic Claude and Google Gemini APIs (API Key & OAuth Bearer),
    GET/POST model discovery and completions, SSE streaming, and multi-instance attribution.
    """

    CLAUDE_PLACEHOLDER_KEYS = {
        "",
        "proxy",
        "dummy",
        "local",
        "vault",
        "aium",
        "none",
        "null",
        "test",
        "default",
        "claude",
        "auto",
    }

    @property
    def claude_provider(self):
        return getattr(self.server, "claude_provider", None)

    @property
    def gemini_provider(self):
        return getattr(self.server, "gemini_provider", None)

    @property
    def database(self):
        return getattr(self.server, "database", None) or getattr(
            self.claude_provider, "db", None
        )

    @staticmethod
    def _extract_sse_tokens(sse_bytes: Union[bytes, str]) -> SSEResult:
        return extract_sse_tokens(sse_bytes)

    def log_message(self, format, *args):
        # Suppress noisy standard HTTP access logs
        pass

    def _open_upstream(self, req: urllib.request.Request, timeout: float = 120.0):
        """Executes the upstream HTTP request. Extracted for clean unit test interception."""
        return urllib.request.urlopen(req, timeout=timeout)

    def _get_client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if hasattr(self, "client_address") and self.client_address:
            return self.client_address[0]
        return "127.0.0.1"

    def _get_instance_id(self, default_id: str = "transparent-proxy") -> str:
        return (
            self.headers.get("X-AIUM-Instance")
            or self.headers.get("X-Instance-ID")
            or self.headers.get("X-Client-Instance")
            or default_id
        )

    def get_managed_nodes(self) -> List[Dict[str, Any]]:
        """Queries registered worker nodes from database."""
        proxy_srv = getattr(self.server, "_proxy_server_instance", None)
        if proxy_srv and hasattr(proxy_srv, "get_managed_nodes"):
            return proxy_srv.get_managed_nodes()
        db = self.database
        if not db:
            return []
        if hasattr(db, "get_managed_nodes"):
            return db.get_managed_nodes()
        if hasattr(db, "list_managed_nodes"):
            return db.list_managed_nodes()
        try:
            conn = db._get_connection() if hasattr(db, "_get_connection") else None
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM managed_nodes")
                rows = [dict(r) for r in cursor.fetchall()]
                conn.close()
                return rows
        except Exception:
            pass
        return []

    def check_budget_circuit_breaker(
        self, provider: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Checks hourly and session spend against configured circuit breaker limits."""
        return evaluate_budget_circuit_breaker(self.database, provider, session_id)

    def resolve_spillover_target(
        self, provider: str
    ) -> Optional[Dict[str, Any]]:
        """Checks cloud quota saturation or error state and resolves healthy LAN failover node."""
        return evaluate_spillover_target(self.database, provider, self)

    def _is_gemini_request(self) -> bool:
        """
        Determines whether the incoming proxy request targets Google Gemini
        (AI Studio / Generative Language API) rather than Anthropic Claude.
        """
        path_lower = (self.path or "").lower()
        header_keys_lower = {k.lower() for k in self.headers.keys()}

        # Explicit mock or Google header
        if (
            self.headers.get("x-mock-gemini-response") == "true"
            or "x-goog-api-key" in header_keys_lower
        ):
            return True

        # Explicit Claude headers take precedence if path is generic /v1/models
        if "anthropic-version" in header_keys_lower or "x-api-key" in header_keys_lower:
            if not (
                "/v1beta/" in path_lower
                or ":generatecontent" in path_lower
                or ":streamgeneratecontent" in path_lower
                or "/models/gemini" in path_lower
            ):
                return False

        return (
            "/v1beta/" in path_lower
            or "/v1/models" in path_lower
            or path_lower.startswith("/models")
            or ":generatecontent" in path_lower
            or ":streamgeneratecontent" in path_lower
            or ":counttokens" in path_lower
            or ":embedcontent" in path_lower
            or ":batchgeneratecontent" in path_lower
            or "key=" in path_lower
        )

    def _prepare_gemini_upstream(self) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
        """
        Normalizes the Gemini upstream path/query, resolves credentials via DPAPI vault
        (replacing placeholder keys like 'proxy' or 'dummy'), and injects the appropriate
        authentication header (`x-goog-api-key` or `Authorization: Bearer`).
        """
        raw_path = self.path or "/"
        parsed = urllib.parse.urlsplit(raw_path)
        norm_path = parsed.path or "/"

        # Normalize keyless /models/... paths to /v1beta/models/...
        if norm_path == "/models" or norm_path.startswith("/models/"):
            norm_path = "/v1beta" + norm_path

        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query_key_val = ""
        filtered_query_pairs = []
        for k, v in query_pairs:
            if k.lower() == "key":
                query_key_val = v
            else:
                filtered_query_pairs.append((k, v))

        upstream_headers: Dict[str, str] = {}
        header_key_val = ""
        auth_header_val = ""
        for k, v in self.headers.items():
            k_low = k.lower()
            if k_low in ("host", "content-length"):
                continue
            if k_low == "x-goog-api-key":
                header_key_val = v
                continue
            if k_low == "authorization":
                auth_header_val = v
                continue
            upstream_headers[k] = v

        client_key = query_key_val or header_key_val
        gemini_prov = getattr(self.server, "gemini_provider", None)

        resolved_info: Dict[str, Any] = {
            "credential": client_key if not GeminiProvider.is_placeholder_key(client_key) else None,
            "auth_type": "api_key" if client_key else "none",
            "token_id": "tok_gem_flash",
            "account_id": "default",
            "project_id": None,
            "source": "fallback",
            "replaced_placeholder": GeminiProvider.is_placeholder_key(client_key),
        }

        if gemini_prov and hasattr(gemini_prov, "resolve_proxy_credential"):
            resolved_info = gemini_prov.resolve_proxy_credential(
                client_key=client_key,
                client_auth_header=auth_header_val,
            )
        elif gemini_prov:
            # Fallback if a mock/custom gemini_provider is injected in tests
            if hasattr(gemini_prov, "resolve_token_id_from_key"):
                resolved_info["token_id"] = gemini_prov.resolve_token_id_from_key(client_key)

        cred = resolved_info.get("credential")
        auth_type = resolved_info.get("auth_type", "none")

        if auth_type == "oauth_bearer" and cred:
            upstream_headers["Authorization"] = f"Bearer {cred}"
        elif auth_type == "api_key" and cred:
            upstream_headers["x-goog-api-key"] = cred
            # If the client originally used ?key= in URL, keep query key updated with real key
            if query_key_val:
                filtered_query_pairs.append(("key", cred))
        elif auth_header_val and not GeminiProvider.is_placeholder_key(auth_header_val):
            upstream_headers["Authorization"] = auth_header_val

        rebuilt_query = urllib.parse.urlencode(filtered_query_pairs)
        final_path = f"{norm_path}?{rebuilt_query}" if rebuilt_query else norm_path
        upstream_url = "https://generativelanguage.googleapis.com" + final_path
        return upstream_url, upstream_headers, resolved_info

    def _resolve_claude_upstream_headers(self) -> Dict[str, str]:
        """
        Prepares upstream headers for Anthropic Claude API requests, replacing
        missing or placeholder `x-api-key` values with the DPAPI vaulted key.
        """
        upstream_headers: Dict[str, str] = {}
        client_api_key = ""
        for k, v in self.headers.items():
            k_low = k.lower()
            if k_low in ("host", "content-length"):
                continue
            if k_low == "x-api-key":
                client_api_key = v.strip()
                continue
            upstream_headers[k] = v

        is_placeholder = client_api_key.lower() in self.CLAUDE_PLACEHOLDER_KEYS
        if not client_api_key or is_placeholder:
            stored_key = None
            claude_prov = getattr(self.server, "claude_provider", None)
            if claude_prov:
                db = getattr(claude_prov, "db", None)
                vault = getattr(claude_prov, "vault", None)
                if db and vault and hasattr(db, "get_active_account_profile"):
                    try:
                        active_acct = db.get_active_account_profile("claude")
                        if active_acct and active_acct.get("account_id"):
                            stored_key = vault.get_credential("claude", active_acct["account_id"])
                    except Exception:
                        pass
                if not stored_key and vault:
                    stored_key = vault.get_credential("claude", "default")
            if stored_key:
                upstream_headers["x-api-key"] = stored_key
            elif client_api_key and not is_placeholder:
                upstream_headers["x-api-key"] = client_api_key
        else:
            upstream_headers["x-api-key"] = client_api_key

        if "anthropic-version" not in {k.lower() for k in upstream_headers.keys()}:
            upstream_headers["anthropic-version"] = "2023-06-01"

        return upstream_headers

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "status": "UP",
                "proxy_target": "claude",
                "proxy_targets": ["claude", "gemini"],
                "listening_port": self.server.server_port,
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        # Support GET requests for Gemini model discovery & auth handshakes (/v1beta/models, /v1/models, /models)
        if self._is_gemini_request():
            upstream_url, upstream_headers, resolved_info = self._prepare_gemini_upstream()

            if self.headers.get("x-mock-gemini-response") == "true":
                mock_models = {
                    "models": [
                        {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro"},
                        {"name": "models/gemini-2.0-flash", "displayName": "Gemini 2.0 Flash"},
                        {"name": "models/gemini-1.5-pro", "displayName": "Gemini 1.5 Pro"},
                    ],
                    "proxy_auth": {
                        "auth_type": resolved_info.get("auth_type"),
                        "source": resolved_info.get("source"),
                        "token_id": resolved_info.get("token_id"),
                        "replaced_placeholder": resolved_info.get("replaced_placeholder"),
                    },
                }
                body_bytes = json.dumps(mock_models).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                self.wfile.write(body_bytes)
                return

            try:
                req = urllib.request.Request(
                    upstream_url,
                    headers=upstream_headers,
                    method="GET",
                )
                with self._open_upstream(req, timeout=30.0) as resp:
                    resp_body = resp.read()
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ["content-encoding", "transfer-encoding"]:
                            self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(resp_body)
                    return
            except urllib.error.HTTPError as e:
                err_body = e.read()
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err_body)
                return
            except Exception as e:
                self.send_error(502, f"Bad Gateway (Gemini GET): {e}")
                return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        start_ts = time.time()
        client_ip = self._get_client_ip()
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b""

        # Budget Circuit Breaker Verification (AIUM-1011)
        prov_target = "gemini" if self._is_gemini_request() else "claude"
        sess_hdr = self.headers.get("X-Session-ID") or self.headers.get("X-AIUM-Session")
        cb_status = self.check_budget_circuit_breaker(prov_target, session_id=sess_hdr)
        if cb_status.get("tripped"):
            spillover = self.resolve_spillover_target(prov_target)
            if not spillover:
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                err_resp = json.dumps({
                    "error": {
                        "type": "budget_circuit_breaker_tripped",
                        "message": cb_status.get("reason", "Budget circuit breaker tripped"),
                        "hourly_spend_usd": cb_status.get("hourly_spend_usd", 0.0),
                        "budget_limit_usd": cb_status.get("budget_limit_usd", 0.0),
                    }
                }).encode("utf-8")
                self.send_header("Content-Length", str(len(err_resp)))
                self.end_headers()
                self.wfile.write(err_resp)
                return

        if self._is_gemini_request():
            upstream_url, upstream_headers, resolved_info = self._prepare_gemini_upstream()
            instance_id = self._get_instance_id(default_id="gemini-proxy")
            m_model = re.search(r"/models/([^:?/]+)", self.path or "")
            model_name = m_model.group(1) if m_model else "gemini-2.0-flash"
            token_id = resolved_info.get("token_id") or "tok_gem_flash"
            project_id = resolved_info.get("project_id")

            # 1. Gemini Mock Response Mode
            if self.headers.get("x-mock-gemini-response") == "true":
                in_tok = int(self.headers.get("x-mock-input-tokens", 100))
                out_tok = int(self.headers.get("x-mock-output-tokens", 50))
                cache_tok = int(self.headers.get("x-mock-cache-tokens", 0))

                if hasattr(self.server, "gemini_provider") and self.server.gemini_provider:
                    self.server.gemini_provider.ingest_proxy_interaction(
                        model=model_name,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        cache_read_tokens=cache_tok,
                        token_id=token_id,
                        client_ip=client_ip,
                        instance_id=instance_id,
                        project_id=project_id,
                        latency_ms=round((time.time() - start_ts) * 1000.0, 2),
                    )

                mock_response = {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": "Mock response proxied from Google Gemini."}],
                                "role": "model",
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": in_tok,
                        "candidatesTokenCount": out_tok,
                        "cachedContentTokenCount": cache_tok,
                        "totalTokenCount": in_tok + out_tok,
                    },
                    "proxyAuth": {
                        "auth_type": resolved_info.get("auth_type"),
                        "source": resolved_info.get("source"),
                        "token_id": token_id,
                        "replaced_placeholder": resolved_info.get("replaced_placeholder"),
                    },
                }
                body_bytes = json.dumps(mock_response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                self.wfile.write(body_bytes)
                return

            # 2. Gemini Real Upstream Proxying
            try:
                req = urllib.request.Request(
                    upstream_url,
                    data=raw_body,
                    headers=upstream_headers,
                    method="POST",
                )
                with self._open_upstream(req, timeout=120.0) as resp:
                    resp_headers = dict(resp.headers)
                    content_type = resp_headers.get("content-type", "")

                    if "text/event-stream" in content_type:
                        # SSE Streaming Passthrough for Gemini
                        self.send_response(resp.status)
                        for k, v in resp.headers.items():
                            if k.lower() not in ["content-encoding", "transfer-encoding"]:
                                self.send_header(k, v)
                        self.end_headers()

                        in_t = 0
                        out_t = 0
                        cache_t = 0
                        for line in resp:
                            self.wfile.write(line)
                            self.wfile.flush()
                            line_str = line.decode("utf-8", errors="replace").strip()
                            if line_str.startswith("data:"):
                                try:
                                    payload = json.loads(line_str[5:].strip())
                                    u = payload.get("usageMetadata", {})
                                    if u:
                                        in_t = u.get("promptTokenCount", in_t)
                                        out_t = u.get("candidatesTokenCount", out_t)
                                        cache_t = u.get("cachedContentTokenCount", cache_t)
                                except Exception:
                                    pass

                        if (
                            hasattr(self.server, "gemini_provider")
                            and self.server.gemini_provider
                            and (in_t > 0 or out_t > 0)
                        ):
                            self.server.gemini_provider.ingest_proxy_interaction(
                                model=model_name,
                                input_tokens=in_t,
                                output_tokens=out_t,
                                cache_read_tokens=cache_t,
                                token_id=token_id,
                                client_ip=client_ip,
                                instance_id=instance_id,
                                project_id=project_id,
                                latency_ms=round((time.time() - start_ts) * 1000.0, 2),
                            )
                        return

                    resp_body = resp.read()
                    try:
                        resp_data = json.loads(resp_body.decode("utf-8"))
                        if (
                            "usageMetadata" in resp_data
                            and hasattr(self.server, "gemini_provider")
                            and self.server.gemini_provider
                        ):
                            u = resp_data["usageMetadata"]
                            in_t = u.get("promptTokenCount", 0)
                            out_t = u.get("candidatesTokenCount", 0)
                            cache_t = u.get("cachedContentTokenCount", 0)
                            self.server.gemini_provider.ingest_proxy_interaction(
                                model=model_name,
                                input_tokens=in_t,
                                output_tokens=out_t,
                                cache_read_tokens=cache_t,
                                token_id=token_id,
                                client_ip=client_ip,
                                instance_id=instance_id,
                                project_id=project_id,
                                latency_ms=round((time.time() - start_ts) * 1000.0, 2),
                            )
                    except Exception:
                        pass

                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ["content-encoding", "transfer-encoding"]:
                            self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(resp_body)
                    return
            except urllib.error.HTTPError as e:
                err_body = e.read()
                if hasattr(self.server, "gemini_provider") and self.server.gemini_provider:
                    diag = getattr(self.server.gemini_provider, "diagnostics", None)
                    if diag:
                        diag.record_error(
                            ErrorCategory.AUTH_FAILURE if e.code in (401, 403) else ErrorCategory.SYSTEM_ERROR,
                            "gemini",
                            f"Gemini proxy upstream HTTP error {e.code}: {e.reason}",
                            {"status_code": e.code, "auth_source": resolved_info.get("source")},
                        )
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err_body)
                return
            except Exception as e:
                self.send_error(502, f"Bad Gateway (Gemini): {e}")
                return

        # =====================================================================
        # ANTHROPIC CLAUDE PROXY HANDLING
        # =====================================================================

        # 1. Test / Mock Streaming Mode
        if self.headers.get("x-mock-stream") == "true":
            in_tok = int(self.headers.get("x-mock-input-tokens", 100))
            out_tok = int(self.headers.get("x-mock-output-tokens", 50))
            model_name = "claude-3-7-sonnet"
            try:
                data = json.loads(raw_body.decode("utf-8"))
                model_name = data.get("model", model_name)
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            events = [
                f'event: message_start\ndata: {{"type": "message_start", "message": {{"id": "msg_stream_1", "type": "message", "role": "assistant", "model": "{model_name}", "usage": {{"input_tokens": {in_tok}, "output_tokens": 1}}}}}}\n\n',
                f'event: content_block_start\ndata: {{"type": "content_block_start", "index": 0, "content_block": {{"type": "text", "text": ""}}}}\n\n',
                f'event: content_block_delta\ndata: {{"type": "content_block_delta", "index": 0, "delta": {{"type": "text_delta", "text": "Streaming tokens from AI Usage Monitor proxy."}}}}\n\n',
                f'event: message_delta\ndata: {{"type": "message_delta", "delta": {{"stop_reason": "end_turn"}}, "usage": {{"output_tokens": {out_tok}}}}}\n\n',
                f'event: message_stop\ndata: {{"type": "message_stop"}}\n\n',
            ]
            for ev in events:
                self.wfile.write(ev.encode("utf-8"))
                self.wfile.flush()

            mock_id = "msg_stream_1"
            if self.claude_provider:
                self.claude_provider.ingest_proxy_interaction(
                    model=model_name,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    session_id=f"stream_{int(time.time())}",
                    client_ip=client_ip,
                    external_id=mock_id,
                )
            return

        # 2. Test / Mock Non-Streaming Mode
        if self.headers.get("x-mock-response") == "true":
            in_tok = int(self.headers.get("x-mock-input-tokens", 100))
            out_tok = int(self.headers.get("x-mock-output-tokens", 50))
            model_name = "claude-3-7-sonnet"
            try:
                data = json.loads(raw_body.decode("utf-8"))
                model_name = data.get("model", model_name)
            except Exception:
                pass

            mock_id = "msg_mock_proxy_12345"
            if self.claude_provider:
                self.claude_provider.ingest_proxy_interaction(
                    model=model_name,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    session_id=f"cli_proxy_{int(time.time())}",
                    client_ip=client_ip,
                    external_id=mock_id,
                )

            mock_response = {
                "id": mock_id,
                "type": "message",
                "role": "assistant",
                "model": model_name,
                "content": [
                    {"type": "text", "text": "This is a response proxied through AI Usage Monitor."}
                ],
                "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
            }
            body_bytes = json.dumps(mock_response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        # 3. Real Upstream Proxying for Claude
        upstream_url = "https://api.anthropic.com" + self.path
        upstream_headers = self._resolve_claude_upstream_headers()

        try:
            req = urllib.request.Request(
                upstream_url,
                data=raw_body,
                headers=upstream_headers,
                method="POST",
            )
            with self._open_upstream(req, timeout=120.0) as resp:
                resp_headers = dict(resp.headers)
                content_type = resp_headers.get("content-type", "")

                if "text/event-stream" in content_type:
                    # SSE Streaming Passthrough
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ["content-encoding", "transfer-encoding"]:
                            self.send_header(k, v)
                    self.end_headers()

                    in_tokens = 0
                    out_tokens = 0
                    stream_model = "claude"
                    extracted_id = None
                    sse_chunks = []

                    for line in resp:
                        self.wfile.write(line)
                        self.wfile.flush()
                        sse_chunks.append(line)
                        line_str = line.decode("utf-8", errors="replace").strip()
                        if line_str.startswith("data:"):
                            try:
                                payload = json.loads(line_str[5:].strip())
                                if not extracted_id and payload.get("id"):
                                    extracted_id = payload.get("id")
                                p_type = payload.get("type")
                                if p_type == "message_start":
                                    msg = payload.get("message", {})
                                    stream_model = msg.get("model", stream_model)
                                    in_tokens = msg.get("usage", {}).get("input_tokens", 0)
                                    if msg.get("id"):
                                        extracted_id = msg.get("id")
                                elif p_type == "message_delta":
                                    out_tokens = payload.get("usage", {}).get(
                                        "output_tokens", out_tokens
                                    )
                                elif "usage" in payload and payload.get("usage"):
                                    u = payload.get("usage", {})
                                    in_tokens = u.get("prompt_tokens", in_tokens)
                                    out_tokens = u.get("completion_tokens", out_tokens)
                            except Exception:
                                pass

                    if not extracted_id or (in_tokens == 0 and out_tokens == 0):
                        parsed = extract_sse_tokens(b"".join(sse_chunks))
                        in_tokens = in_tokens or parsed.input_tokens
                        out_tokens = out_tokens or parsed.output_tokens
                        extracted_id = extracted_id or parsed.external_id
                        if stream_model == "claude" and parsed.model:
                            stream_model = parsed.model

                    if self.claude_provider:
                        self.claude_provider.ingest_proxy_interaction(
                            model=stream_model,
                            input_tokens=in_tokens,
                            output_tokens=out_tokens,
                            rate_limit_headers=resp_headers,
                            client_ip=client_ip,
                            external_id=extracted_id,
                        )

                else:
                    # Buffered JSON response
                    resp_body = resp.read()
                    extracted_id = None
                    try:
                        resp_json = json.loads(resp_body.decode("utf-8"))
                        usage = resp_json.get("usage", {})
                        in_tok = usage.get("input_tokens", 0)
                        out_tok = usage.get("output_tokens", 0)
                        model_val = resp_json.get("model", "claude")
                        extracted_id = resp_json.get("id")

                        if self.claude_provider:
                            self.claude_provider.ingest_proxy_interaction(
                                model=model_val,
                                input_tokens=in_tok,
                                output_tokens=out_tok,
                                rate_limit_headers=resp_headers,
                                client_ip=client_ip,
                                external_id=extracted_id,
                            )
                    except Exception:
                        pass

                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ["content-encoding", "transfer-encoding"]:
                            self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(resp_body)

        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.server.claude_provider.diagnostics.record_error(
                ErrorCategory.PROXY_BLOCKED if e.code in [403, 407] else ErrorCategory.SYSTEM_ERROR,
                "claude",
                f"Proxy upstream HTTP error {e.code}: {e.reason}",
                {"status_code": e.code},
            )
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            self.server.claude_provider.diagnostics.record_error(
                ErrorCategory.NETWORK_TIMEOUT,
                "claude",
                f"Proxy network error: {e}",
                {"exception": str(e)},
            )
            self.send_error(502, f"Bad Gateway: {e}")


class TransparentProxyServer:
    """
    Transparent Local Proxy Server running in background thread.
    Supports Anthropic Claude and Google Gemini completion proxying.
    """

    def __init__(
        self,
        claude_provider,
        host: str = "127.0.0.1",
        port: int = 8766,
        gemini_provider=None,
        database=None,
    ):
        self.claude_provider = claude_provider
        self.gemini_provider = gemini_provider
        self.database = database or getattr(claude_provider, "db", None)
        self.host = host
        self.port = port
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def server_port(self) -> int:
        if self._server:
            return self._server.server_port
        return self.port

    def get_managed_nodes(self) -> List[Dict[str, Any]]:
        """Queries registered worker nodes from database."""
        db = self.database
        if not db:
            return []
        if hasattr(db, "get_managed_nodes"):
            return db.get_managed_nodes()
        if hasattr(db, "list_managed_nodes"):
            return db.list_managed_nodes()
        try:
            conn = db._get_connection() if hasattr(db, "_get_connection") else None
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM managed_nodes")
                rows = [dict(r) for r in cursor.fetchall()]
                conn.close()
                return rows
        except Exception:
            pass
        return []

    def check_budget_circuit_breaker(
        self, provider: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Checks hourly and session spend against configured circuit breaker limits."""
        return evaluate_budget_circuit_breaker(self.database, provider, session_id)

    def resolve_spillover_target(
        self, provider: str
    ) -> Optional[Dict[str, Any]]:
        """Checks cloud quota saturation or error state and resolves healthy LAN failover node."""
        return evaluate_spillover_target(self.database, provider, self)

    def start(self):
        server_address = (self.host, self.port)
        self._server = http.server.ThreadingHTTPServer(server_address, TransparentProxyHandler)
        self._server.claude_provider = self.claude_provider
        self._server.gemini_provider = self.gemini_provider
        self._server.database = self.database
        self._server._proxy_server_instance = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
