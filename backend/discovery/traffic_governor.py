import threading
import time
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List, Tuple

class TrafficGovernor:
    """
    Traffic Manager & Resource Governor for remote AI nodes.
    Prevents overwhelming remote machines via concurrency semaphores, FIFO queuing,
    timeout shedding, circuit breaker resilience, and real-time telemetry recording.
    Supports pool routing across trusted nodes with automatic failover and context-aware query dispatch.
    """

    def __init__(self, registry, database):
        self.registry = registry
        self.db = database
        self._semaphores: Dict[str, threading.Semaphore] = {}
        self._semaphore_limits: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._stats: Dict[str, Dict[str, Any]] = {}

    def _get_semaphore(self, node_id: str, max_concurrency: int) -> threading.Semaphore:
        with self._lock:
            current_limit = self._semaphore_limits.get(node_id)
            if node_id not in self._semaphores or current_limit != max_concurrency:
                self._semaphores[node_id] = threading.Semaphore(max_concurrency)
                self._semaphore_limits[node_id] = max_concurrency
            return self._semaphores[node_id]

    def _get_node_stats(self, node_id: str) -> Dict[str, Any]:
        with self._lock:
            if node_id not in self._stats:
                self._stats[node_id] = {
                    "active_requests": 0,
                    "queued_requests": 0,
                    "total_requests": 0,
                    "total_tokens_routed": 0,
                    "circuit_breaker_failures": 0,
                    "last_failure_time": 0.0
                }
            return self._stats[node_id]

    def check_client_allowance(
        self,
        client_ip: str,
        requested_tokens: int = 0,
        model_name: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Enforces per-client token limits (sliding burst window & daily rolling quota),
        temporary/scheduled elevated bypasses, and model/node restrictions.
        """
        if not client_ip or not self.db or not hasattr(self.db, "get_client_quota"):
            return True, None, {}

        quota = self.db.get_client_quota(client_ip)
        usage = self.db.get_client_token_usage(client_ip)

        # 0. Explicit client block or zero allowance check
        if quota.get("is_blocked") in [1, True, "1"] or quota.get("session_token_limit") == 0:
            return False, f"Client {client_ip} is Blocked from proxy access.", {"reason": "client_blocked", "is_blocked": True}

        # 1. Bypass checks (unrestricted, temporary countdown, scheduled window)
        if self.db.is_client_bypass_active(quota):
            return True, None, {"bypass_active": True}

        # 2. Model restriction check
        if model_name:
            blocked_models = quota.get("blocked_models") or []
            if any(b.lower() == model_name.lower() for b in blocked_models):
                return False, f"Model restricted for client {client_ip}: '{model_name}' is blocked.", {"reason": "model_restricted"}

            allowed_models = quota.get("allowed_models") or []
            if allowed_models and not any(a.lower() == model_name.lower() for a in allowed_models):
                return False, f"Model restricted for client {client_ip}: '{model_name}' is not in allowed list.", {"reason": "model_restricted"}

        # 3. Node restriction check
        if node_id and node_id not in ["pool", "active_compute"]:
            blocked_nodes = quota.get("blocked_nodes") or []
            if any(b == node_id for b in blocked_nodes):
                return False, f"Node restricted for client {client_ip}: '{node_id}' is blocked.", {"reason": "node_restricted"}

            allowed_nodes = quota.get("allowed_nodes") or []
            if allowed_nodes and not any(a == node_id for a in allowed_nodes):
                return False, f"Node restricted for client {client_ip}: '{node_id}' is not in allowed list.", {"reason": "node_restricted"}

        # 4. Sliding Session Burst Window check
        sess_used = usage.get("session_tokens_used", 0)
        sess_limit = quota.get("session_token_limit", 25000)
        if (sess_used + requested_tokens) > sess_limit:
            rem = max(0, sess_limit - sess_used)
            window_mins = quota.get("session_window_minutes", 15)
            err = (
                f"Burst Window Quota Exceeded: Client {client_ip} has consumed {sess_used:,} tokens "
                f"in the {window_mins}m window (limit: {sess_limit:,}). Remaining: {rem:,}."
            )
            return False, err, {
                "retry_after_reason": "burst_window_limit",
                "tokens_remaining": rem,
                "window_minutes": window_mins,
                "limit": sess_limit,
                "used": sess_used
            }

        # 5. Daily Rolling Quota check
        daily_used = usage.get("daily_tokens_used", 0)
        daily_limit = quota.get("daily_token_limit", 250000)
        if (daily_used + requested_tokens) > daily_limit:
            rem = max(0, daily_limit - daily_used)
            err = (
                f"Daily Token Quota Exceeded: Client {client_ip} has consumed {daily_used:,} tokens "
                f"today (limit: {daily_limit:,}). Remaining: {rem:,}."
            )
            return False, err, {
                "retry_after_reason": "daily_limit",
                "tokens_remaining": rem,
                "limit": daily_limit,
                "used": daily_used
            }

        return True, None, {
            "session_tokens_remaining": usage.get("session_tokens_remaining"),
            "daily_tokens_remaining": usage.get("daily_tokens_remaining")
        }

    def forward_completion(
        self,
        node_id: str,
        model: str,
        prompt: str,
        stream: bool = False,
        extra_payload: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Routes an inference request through concurrency-limited FIFO queue with timeout shedding.
        If node_id is 'pool' or 'active_compute', routes to the highest-priority trusted active node
        with automatic failover to healthy candidates.
        """
        # Client Quota / Burst Window Pre-check
        if client_ip:
            allowed, err, details = self.check_client_allowance(
                client_ip=client_ip,
                requested_tokens=0,
                model_name=model,
                node_id=node_id
            )
            if not allowed:
                return {
                    "success": False,
                    "error": err,
                    "status_code": 429 if "Quota Exceeded" in (err or "") else 403,
                    "details": details or {}
                }

        # 1. Pool Routing & Failover
        if node_id in ["pool", "active_compute"]:
            candidates = self.registry.list_nodes()
            # Strictly filter for trusted nodes in Active Compute group
            active_trusted = [
                n for n in candidates
                if n.get("is_trusted", 1) == 1
                and n.get("compute_group", "Active Compute") == "Active Compute"
                and n.get("status", "ONLINE") != "OFFLINE"
            ]
            if not active_trusted:
                return {
                    "success": False,
                    "error": "No active trusted nodes available in Active Compute pool."
                }

            # Sort by priority DESC
            active_trusted.sort(key=lambda x: int(x.get("priority", 5)), reverse=True)

            last_err = "No candidates succeeded"
            for cand in active_trusted:
                cand_id = cand["id"]
                cand_stats = self._get_node_stats(cand_id)
                if cand_stats["circuit_breaker_failures"] >= 3:
                    if time.time() - cand_stats["last_failure_time"] < 30.0:
                        continue  # Skip currently tripped node during failover sweep

                res = self._execute_node_request(
                    node=cand,
                    model=model,
                    prompt=prompt,
                    stream=stream,
                    extra_payload=extra_payload,
                    timeout=timeout,
                    client_ip=client_ip
                )
                if res.get("success"):
                    res["pool_routed"] = True
                    return res
                last_err = res.get("error", "Unknown error")

            return {
                "success": False,
                "error": f"Active Compute pool failover exhausted: {last_err}"
            }

        # 2. Direct Node Routing
        node = self.registry.get_node(node_id)
        if not node:
            return {"success": False, "error": f"Node '{node_id}' not found in registry."}

        return self._execute_node_request(
            node=node,
            model=model,
            prompt=prompt,
            stream=stream,
            extra_payload=extra_payload,
            timeout=timeout,
            client_ip=client_ip
        )

    def _execute_node_request(
        self,
        node: Dict[str, Any],
        model: str,
        prompt: str,
        stream: bool = False,
        extra_payload: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        node_id = node["id"]
        stats = self._get_node_stats(node_id)

        # 1. Circuit breaker check
        if stats["circuit_breaker_failures"] >= 3:
            time_since_err = time.time() - stats["last_failure_time"]
            if time_since_err < 30.0:
                return {
                    "success": False,
                    "error": f"Node '{node_id}' circuit breaker tripped ({stats['circuit_breaker_failures']} consecutive errors). Cooldown remaining: {30.0 - time_since_err:.1f}s"
                }

        max_concur = int(node.get("max_concurrency", 1))
        sem = self._get_semaphore(node_id, max_concur)
        queue_timeout = timeout if timeout is not None else float(node.get("queue_timeout_seconds", 30.0))

        # 2. Enqueue & Semaphore Acquisition
        q_start = time.time()
        with self._lock:
            stats["queued_requests"] += 1

        acquired = sem.acquire(timeout=queue_timeout)

        with self._lock:
            stats["queued_requests"] -= 1

        if not acquired:
            return {
                "success": False,
                "error": f"Node '{node_id}' queue timeout: exceeded {queue_timeout:.1f}s queue wait ceiling."
            }

        queue_wait_ms = (time.time() - q_start) * 1000.0

        with self._lock:
            stats["active_requests"] += 1

        endpoint = node.get("endpoint", "").rstrip("/")
        engine = node.get("engine", "ollama")

        try:
            # 3. Upstream Dispatch
            if engine == "ollama":
                target_url = f"{endpoint}/api/generate"
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": stream
                }
                if extra_payload:
                    payload.update(extra_payload)
            else:
                target_url = f"{endpoint}/v1/chat/completions"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": stream
                }
                if extra_payload:
                    payload.update(extra_payload)

            req_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                target_url,
                data=req_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=120.0) as resp:
                resp_bytes = resp.read()
                resp_json = json.loads(resp_bytes.decode("utf-8"))

                # 4. Token Parsing
                if engine == "ollama":
                    in_tok = int(resp_json.get("prompt_eval_count") or len(prompt) // 4 or 10)
                    out_tok = int(resp_json.get("eval_count") or 50)
                    text_resp = resp_json.get("response", "")
                else:
                    usage = resp_json.get("usage", {})
                    in_tok = int(usage.get("prompt_tokens") or len(prompt) // 4 or 10)
                    out_tok = int(usage.get("completion_tokens") or 50)
                    choices = resp_json.get("choices", [])
                    text_resp = choices[0].get("message", {}).get("content", "") if choices else ""

                # Reset failure count on success
                with self._lock:
                    stats["circuit_breaker_failures"] = 0
                    stats["total_requests"] += 1
                    stats["total_tokens_routed"] += (in_tok + out_tok)

                if node.get("status") == "UNHEALTHY":
                    self.registry.update_node_status(node_id, "ONLINE")

                # Ingest into SQLite usage_events
                if self.db:
                    self.db.record_usage_event(
                        provider="ollama", # maps to zero-cost local / remote hardware
                        model=model,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        session_id=f"remote_{node_id}_{int(time.time())}",
                        estimated_cost=0.0,
                        source="proxy",
                        instance_id=node_id,
                        is_proxied=1,
                        client_ip=client_ip
                    )
                    if client_ip and hasattr(self.db, "record_client_tokens"):
                        self.db.record_client_tokens(client_ip, in_tok + out_tok)

                return {
                    "success": True,
                    "node_id": node_id,
                    "node_name": node.get("name", "Node"),
                    "model": model,
                    "response": text_resp,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "total_tokens": in_tok + out_tok,
                    "queue_time_ms": round(queue_wait_ms, 1),
                    "raw": resp_json
                }

        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            with self._lock:
                stats["circuit_breaker_failures"] += 1
                stats["last_failure_time"] = time.time()
                if stats["circuit_breaker_failures"] >= 3:
                    self.registry.update_node_status(node_id, "UNHEALTHY")

            return {
                "success": False,
                "error": f"HTTP {e.code}: {e.reason} ({err_msg})",
                "status_code": e.code,
                "queue_time_ms": round(queue_wait_ms, 1)
            }
        except Exception as e:
            with self._lock:
                stats["circuit_breaker_failures"] += 1
                stats["last_failure_time"] = time.time()
                if stats["circuit_breaker_failures"] >= 3:
                    self.registry.update_node_status(node_id, "UNHEALTHY")

            return {
                "success": False,
                "error": str(e),
                "queue_time_ms": round(queue_wait_ms, 1)
            }
        finally:
            with self._lock:
                stats["active_requests"] -= 1
            sem.release()

    def forward_query_with_context(
        self,
        target: str,
        prompt: str,
        files: Optional[List[Dict[str, Any]]] = None,
        model: str = "default",
        stream: bool = False,
        timeout: Optional[float] = None,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Builds a file-context enriched prompt, evaluates whether the target is an untrusted node,
        and forwards the query through the traffic governor.
        """
        # Format file attachments as markdown context blocks
        full_prompt = ""
        if files:
            full_prompt += "=== ATTACHED CONTEXT FILES ===\n"
            for f in files:
                fname = f.get("filename", "context_file.txt")
                fcontent = f.get("content", "")
                full_prompt += f"\n--- START FILE: {fname} ---\n{fcontent}\n--- END FILE: {fname} ---\n"
            full_prompt += "\n=== USER INSTRUCTION / QUERY ===\n"
        full_prompt += prompt

        # Check target trust
        is_untrusted = False
        target_node_id = target
        if target.startswith("node:"):
            target_node_id = target[5:]
        elif target in ["pool", "active_compute"]:
            target_node_id = "pool"

        if target_node_id != "pool":
            target_node = self.registry.get_node(target_node_id)
            if target_node and target_node.get("is_trusted", 1) == 0:
                is_untrusted = True

        res = self.forward_completion(
            node_id=target_node_id,
            model=model,
            prompt=full_prompt,
            stream=stream,
            timeout=timeout,
            client_ip=client_ip
        )

        res["is_untrusted_warning"] = is_untrusted
        if is_untrusted:
            res["warning_message"] = (
                "⚠️ UNTRUSTED RESOURCE: This device has been designated as UNTRUSTED. "
                "Sensitive files or confidential data should not be dispatched to this node, "
                "and model responses should not be considered verified."
            )
        else:
            res["warning_message"] = ""

        return res

    def get_telemetry(self, node_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns live active, queued, and historical token telemetry."""
        with self._lock:
            if node_id:
                base = self._stats.get(node_id, {
                    "active_requests": 0,
                    "queued_requests": 0,
                    "total_requests": 0,
                    "total_tokens_routed": 0,
                    "circuit_breaker_failures": 0
                })
                return dict(base)

            # Aggregate across all nodes
            total_active = sum(s["active_requests"] for s in self._stats.values())
            total_queued = sum(s["queued_requests"] for s in self._stats.values())
            total_reqs = sum(s["total_requests"] for s in self._stats.values())
            total_tokens = sum(s["total_tokens_routed"] for s in self._stats.values())
            return {
                "active_requests": total_active,
                "queued_requests": total_queued,
                "total_requests": total_reqs,
                "total_tokens_routed": total_tokens,
                "nodes": {nid: dict(st) for nid, st in self._stats.items()}
            }

    def _select_candidate_nodes(
        self,
        model_name: Optional[str] = None,
        preferred_node_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Selects candidate nodes, prioritizing direct model hosts and sorting by priority DESC.
        """
        if preferred_node_id and preferred_node_id not in ["pool", "active_compute"]:
            n = self.registry.get_node(preferred_node_id)
            return [n] if n else []

        all_nodes = self.registry.list_nodes()
        active_trusted = [
            n for n in all_nodes
            if n.get("is_trusted", 1) == 1
            and n.get("compute_group", "Active Compute") == "Active Compute"
            and n.get("status", "ONLINE") != "OFFLINE"
        ]

        if not active_trusted:
            return []

        if model_name and model_name != "default":
            def node_has_model(node):
                models = node.get("models") or []
                for m in models:
                    m_name = m.get("name") if isinstance(m, dict) else str(m)
                    if not m_name:
                        continue
                    m_lower = m_name.lower()
                    target_lower = model_name.lower()
                    if m_lower == target_lower:
                        return True
                    if m_lower.startswith(target_lower + ":") or target_lower.startswith(m_lower + ":"):
                        return True
                return False

            matching = [n for n in active_trusted if node_has_model(n)]
            others = [n for n in active_trusted if not node_has_model(n)]
            matching.sort(key=lambda x: int(x.get("priority", 5)), reverse=True)
            others.sort(key=lambda x: int(x.get("priority", 5)), reverse=True)
            return matching + others
        else:
            active_trusted.sort(key=lambda x: int(x.get("priority", 5)), reverse=True)
            return active_trusted

    def forward_ollama_request(
        self,
        endpoint_path: str,
        payload: Dict[str, Any],
        client_ip: Optional[str] = None,
        timeout: Optional[float] = None,
        preferred_node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Forwards a standard Ollama REST API request to candidate worker nodes with
        model-targeted routing, circuit-breaker failover, concurrency management,
        client quota checks, and token telemetry recording.
        """
        model_name = payload.get("model") or payload.get("name") or "default"

        # 1. Client Quota / Burst Window Pre-check
        if client_ip:
            allowed, err, details = self.check_client_allowance(
                client_ip=client_ip,
                requested_tokens=0,
                model_name=model_name if model_name != "default" else None,
                node_id=preferred_node_id
            )
            if not allowed:
                return {
                    "success": False,
                    "error": err,
                    "status_code": 429 if "Quota Exceeded" in (err or "") else 403,
                    "details": details or {}
                }

        # 2. Candidate Selection
        candidates = self._select_candidate_nodes(model_name=model_name, preferred_node_id=preferred_node_id)
        if not candidates:
            return {
                "success": False,
                "status_code": 503,
                "error": "No active trusted worker nodes available in cluster."
            }

        last_err = "No worker nodes succeeded"
        last_code = 503

        # 3. Failover Loop
        for cand in candidates:
            cand_id = cand["id"]
            cand_stats = self._get_node_stats(cand_id)

            # Circuit breaker check
            if cand_stats["circuit_breaker_failures"] >= 3:
                time_since_err = time.time() - cand_stats["last_failure_time"]
                if time_since_err < 30.0:
                    continue  # Cooldown active, skip node

            max_concur = int(cand.get("max_concurrency", 1))
            sem = self._get_semaphore(cand_id, max_concur)
            queue_timeout = timeout if timeout is not None else float(cand.get("queue_timeout_seconds", 30.0))

            with self._lock:
                cand_stats["queued_requests"] += 1

            acquired = sem.acquire(timeout=queue_timeout)

            with self._lock:
                cand_stats["queued_requests"] -= 1

            if not acquired:
                last_err = f"Node '{cand_id}' queue timeout ({queue_timeout}s)"
                last_code = 504
                continue

            with self._lock:
                cand_stats["active_requests"] += 1

            endpoint = cand.get("endpoint", "").rstrip("/")
            target_url = f"{endpoint}{endpoint_path}"

            try:
                req_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    target_url,
                    data=req_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=timeout or 60.0) as resp:
                    resp_bytes = resp.read()
                    try:
                        resp_json = json.loads(resp_bytes.decode("utf-8"))
                    except Exception:
                        resp_json = {"raw": resp_bytes.decode("utf-8", errors="replace")}

                    # Extract token telemetry
                    in_tok = int(resp_json.get("prompt_eval_count") or len(str(payload)) // 4 or 10)
                    out_tok = int(resp_json.get("eval_count") or 25)

                    with self._lock:
                        cand_stats["circuit_breaker_failures"] = 0
                        cand_stats["total_requests"] += 1
                        cand_stats["total_tokens_routed"] += (in_tok + out_tok)

                    if cand.get("status") == "UNHEALTHY":
                        self.registry.update_node_status(cand_id, "ONLINE")

                    # Ingest into SQLite usage_events
                    if self.db:
                        self.db.record_usage_event(
                            provider="ollama",
                            model=model_name if model_name != "default" else (cand.get("models", [{}])[0].get("name", "llama3:8b") if cand.get("models") else "llama3:8b"),
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                            session_id=f"remote_{cand_id}_{int(time.time())}",
                            estimated_cost=0.0,
                            source="proxy",
                            instance_id=cand_id,
                            is_proxied=1,
                            client_ip=client_ip
                        )
                        if client_ip and hasattr(self.db, "record_client_tokens"):
                            self.db.record_client_tokens(client_ip, in_tok + out_tok)

                    return {
                        "success": True,
                        "status_code": 200,
                        "node_id": cand_id,
                        "data": resp_json
                    }

            except urllib.error.HTTPError as e:
                with self._lock:
                    cand_stats["circuit_breaker_failures"] += 1
                    cand_stats["last_failure_time"] = time.time()
                    if cand_stats["circuit_breaker_failures"] >= 3:
                        self.registry.update_node_status(cand_id, "UNHEALTHY")
                last_err = f"HTTP {e.code}: {e.reason}"
                last_code = e.code
                continue
            except Exception as e:
                with self._lock:
                    cand_stats["circuit_breaker_failures"] += 1
                    cand_stats["last_failure_time"] = time.time()
                    if cand_stats["circuit_breaker_failures"] >= 3:
                        self.registry.update_node_status(cand_id, "UNHEALTHY")
                last_err = str(e)
                last_code = 503
                continue
            finally:
                with self._lock:
                    cand_stats["active_requests"] -= 1
                sem.release()

        return {
            "success": False,
            "status_code": last_code,
            "error": f"Worker node execution failed: {last_err}"
        }

    def stream_ollama_request(
        self,
        endpoint_path: str,
        payload: Dict[str, Any],
        client_ip: Optional[str] = None,
        timeout: Optional[float] = None,
        preferred_node_id: Optional[str] = None
    ) -> Tuple[bool, int, Any]:
        """
        Executes a streaming request to a candidate worker node.
        Returns (success: bool, status_code: int, generator_or_error_dict).
        """
        model_name = payload.get("model") or payload.get("name") or "default"

        # 1. Client Quota / Burst Window Pre-check
        if client_ip:
            allowed, err, details = self.check_client_allowance(
                client_ip=client_ip,
                requested_tokens=0,
                model_name=model_name if model_name != "default" else None,
                node_id=preferred_node_id
            )
            if not allowed:
                return False, 429 if "Quota Exceeded" in (err or "") else 403, {"error": err, "details": details or {}}

        # 2. Candidate Selection
        candidates = self._select_candidate_nodes(model_name=model_name, preferred_node_id=preferred_node_id)
        if not candidates:
            return False, 503, {"error": "No active trusted worker nodes available in cluster."}

        last_err = "No worker nodes succeeded"
        last_code = 503

        # 3. Failover Loop to establish connection
        for cand in candidates:
            cand_id = cand["id"]
            cand_stats = self._get_node_stats(cand_id)

            if cand_stats["circuit_breaker_failures"] >= 3:
                time_since_err = time.time() - cand_stats["last_failure_time"]
                if time_since_err < 30.0:
                    continue

            max_concur = int(cand.get("max_concurrency", 1))
            sem = self._get_semaphore(cand_id, max_concur)
            queue_timeout = timeout if timeout is not None else float(cand.get("queue_timeout_seconds", 30.0))

            with self._lock:
                cand_stats["queued_requests"] += 1

            acquired = sem.acquire(timeout=queue_timeout)

            with self._lock:
                cand_stats["queued_requests"] -= 1

            if not acquired:
                last_err = f"Node '{cand_id}' queue timeout ({queue_timeout}s)"
                last_code = 504
                continue

            with self._lock:
                cand_stats["active_requests"] += 1

            endpoint = cand.get("endpoint", "").rstrip("/")
            target_url = f"{endpoint}{endpoint_path}"

            try:
                req_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    target_url,
                    data=req_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )

                resp = urllib.request.urlopen(req, timeout=timeout or 60.0)

                # Upstream connection established! Generator manages streaming and cleanup
                def generator():
                    tot_in = 0
                    tot_out = 0
                    try:
                        for line in resp:
                            yield line
                            if line.strip():
                                try:
                                    chunk_json = json.loads(line.decode("utf-8"))
                                    if chunk_json.get("done"):
                                        tot_in = int(chunk_json.get("prompt_eval_count") or 10)
                                        tot_out = int(chunk_json.get("eval_count") or 25)
                                        with self._lock:
                                            cand_stats["circuit_breaker_failures"] = 0
                                            cand_stats["total_requests"] += 1
                                            cand_stats["total_tokens_routed"] += (tot_in + tot_out)
                                        if self.db:
                                            self.db.record_usage_event(
                                                provider="ollama",
                                                model=model_name if model_name != "default" else "llama3:8b",
                                                input_tokens=tot_in,
                                                output_tokens=tot_out,
                                                session_id=f"stream_{cand_id}_{int(time.time())}",
                                                estimated_cost=0.0,
                                                source="proxy",
                                                instance_id=cand_id,
                                                is_proxied=1,
                                                client_ip=client_ip
                                            )
                                            if client_ip and hasattr(self.db, "record_client_tokens"):
                                                self.db.record_client_tokens(client_ip, tot_in + tot_out)
                                except Exception:
                                    pass
                    finally:
                        resp.close()
                        with self._lock:
                            cand_stats["active_requests"] -= 1
                        sem.release()

                return True, 200, generator()

            except urllib.error.HTTPError as e:
                with self._lock:
                    cand_stats["circuit_breaker_failures"] += 1
                    cand_stats["last_failure_time"] = time.time()
                    cand_stats["active_requests"] -= 1
                    if cand_stats["circuit_breaker_failures"] >= 3:
                        self.registry.update_node_status(cand_id, "UNHEALTHY")
                sem.release()
                last_err = f"HTTP {e.code}: {e.reason}"
                last_code = e.code
                continue
            except Exception as e:
                with self._lock:
                    cand_stats["circuit_breaker_failures"] += 1
                    cand_stats["last_failure_time"] = time.time()
                    cand_stats["active_requests"] -= 1
                    if cand_stats["circuit_breaker_failures"] >= 3:
                        self.registry.update_node_status(cand_id, "UNHEALTHY")
                sem.release()
                last_err = str(e)
                last_code = 503
                continue

        return False, last_code, {"error": f"Worker node execution failed: {last_err}"}

