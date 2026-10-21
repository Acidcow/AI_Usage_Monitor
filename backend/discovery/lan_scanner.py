import socket
import urllib.request
import urllib.error
import json
import time
import subprocess
import ipaddress
import re
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

STANDARD_AI_PORTS = [11434, 1234, 8000, 8080, 5000, 5001, 8081, 3000]

PLATFORM_CATALOG = {
    "ollama": {
        "name": "Ollama",
        "port": 11434,
        "secondary_ports": [11435],
        "paths": ["/api/version", "/api/tags"],
        "protocol": "HTTP REST",
        "description": "Standard local LLM runtime (Llama 3, DeepSeek, Mistral). Requires OLLAMA_HOST=0.0.0.0 for LAN access."
    },
    "lmstudio": {
        "name": "LM Studio",
        "port": 1234,
        "secondary_ports": [1235],
        "paths": ["/v1/models"],
        "protocol": "HTTP / OpenAI",
        "description": "Local GUI engine exposing an OpenAI-compatible /v1/models server on port 1234."
    },
    "vllm": {
        "name": "vLLM / LocalAI / LiteLLM",
        "port": 8000,
        "secondary_ports": [8080, 8001],
        "paths": ["/v1/models", "/health"],
        "protocol": "HTTP / OpenAI",
        "description": "High-throughput inference server for multi-GPU workstations and clusters."
    },
    "oobabooga": {
        "name": "Text Generation WebUI",
        "port": 5000,
        "secondary_ports": [5001, 7860],
        "paths": ["/v1/models"],
        "protocol": "HTTP / OpenAI",
        "description": "Oobabooga web interface with OpenAI extension enabled."
    },
    "tabby_kobold": {
        "name": "Tabby / KoboldCPP",
        "port": 5001,
        "secondary_ports": [8081, 5002],
        "paths": ["/v1/models", "/api/v1/model"],
        "protocol": "HTTP REST",
        "description": "Self-hosted coding assistant (Tabby) or quantized model runner (Kobold)."
    },
    "open_webui": {
        "name": "Open WebUI",
        "port": 3000,
        "secondary_ports": [8080],
        "paths": ["/api/version", "/"],
        "protocol": "HTTP Web",
        "description": "Browser web front-end connecting to backend Ollama and OpenAI instances."
    }
}

class LANScanner:
    """
    Zero-dependency LAN scanner discovering exposed AI instances (Ollama, LM Studio, vLLM, etc.)
    Features multi-adapter subnet detection, flexible CIDR/range parsing, alias correlation,
    and 3-color state classification.
    """

    def __init__(self, default_timeout: float = 0.25):
        self.default_timeout = default_timeout
        self._alias_cache: Dict[str, str] = {}

    def get_local_adapters_and_subnets(self) -> List[Dict[str, Any]]:
        """
        Detects all active network adapters, assigned IPv4 addresses, and derived CIDR subnets.
        Uses Windows ipconfig parsing with standard socket getaddrinfo fallbacks.
        """
        adapters: List[Dict[str, Any]] = []
        hostname = socket.gethostname()

        # Method A: Windows ipconfig inspection
        try:
            res = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                timeout=2.0
            )
            if res.returncode == 0:
                current_adapter = "Local Area Connection"
                lines = res.stdout.splitlines()
                ipv4_re = re.compile(r"IPv4 Address[ .]*:[ ]*([0-9.]+)")
                mask_re = re.compile(r"Subnet Mask[ .]*:[ ]*([0-9.]+)")
                adapter_header_re = re.compile(r"^[A-Za-z0-9].*adapter (.*):")

                curr_ip = None
                curr_mask = None

                for line in lines:
                    head_m = adapter_header_re.search(line)
                    if head_m:
                        if curr_ip:
                            mask_val = curr_mask or "255.255.255.0"
                            try:
                                net = ipaddress.IPv4Network(f"{curr_ip}/{mask_val}", strict=False)
                                subnet_cidr = str(net)
                            except Exception:
                                subnet_cidr = f"{curr_ip.rsplit('.', 1)[0]}.0/24"
                            adapters.append({
                                "name": current_adapter,
                                "ip": curr_ip,
                                "mask": mask_val,
                                "subnet": subnet_cidr,
                                "hostname": hostname
                            })
                            curr_ip = None
                            curr_mask = None
                        current_adapter = head_m.group(1).strip()

                    ip_m = ipv4_re.search(line)
                    if ip_m:
                        curr_ip = ip_m.group(1).strip()

                    mask_m = mask_re.search(line)
                    if mask_m:
                        curr_mask = mask_m.group(1).strip()

                if curr_ip:
                    mask_val = curr_mask or "255.255.255.0"
                    try:
                        net = ipaddress.IPv4Network(f"{curr_ip}/{mask_val}", strict=False)
                        subnet_cidr = str(net)
                    except Exception:
                        subnet_cidr = f"{curr_ip.rsplit('.', 1)[0]}.0/24"
                    adapters.append({
                        "name": current_adapter,
                        "ip": curr_ip,
                        "mask": mask_val,
                        "subnet": subnet_cidr,
                        "hostname": hostname
                    })
        except Exception:
            pass

        # Method B: Socket fallback if no adapters extracted
        if not adapters:
            seen_ips = set()
            try:
                addr_infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
                for item in addr_infos:
                    ip = item[4][0]
                    if ip not in seen_ips:
                        seen_ips.add(ip)
                        parts = ip.split(".")
                        subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24" if len(parts) == 4 else "127.0.0.0/24"
                        adapters.append({
                            "name": f"Adapter ({ip})",
                            "ip": ip,
                            "mask": "255.255.255.0",
                            "subnet": subnet,
                            "hostname": hostname
                        })
            except Exception:
                pass

        # Always ensure localhost/loopback is represented if nothing else
        if not adapters:
            adapters.append({
                "name": "Loopback",
                "ip": "127.0.0.1",
                "mask": "255.0.0.0",
                "subnet": "127.0.0.0/8",
                "hostname": hostname
            })

        return adapters

    def get_local_subnet_info(self) -> Tuple[str, str]:
        """
        Detects primary local host IPv4 and derived /24 subnet.
        Falls back to 127.0.0.1 / 127.0.0.0/24 if offline or loopback.
        """
        adapters = self.get_local_adapters_and_subnets()
        for a in adapters:
            if not a["ip"].startswith("127."):
                return a["ip"], a["subnet"]
        if adapters:
            return adapters[0]["ip"], adapters[0]["subnet"]
        return "127.0.0.1", "127.0.0.0/24"

    def parse_target_spec(self, target_spec: str, max_hosts: int = 1024) -> List[str]:
        """
        Parses CIDR notation (10.1.7.0/24), IP ranges (10.1.7.50-10.1.7.60),
        hostnames/aliases, and comma-separated hybrid lists into discrete IP addresses.
        Enforces max_hosts safety limit to prevent network flooding on wide masks.
        """
        if not target_spec or not target_spec.strip():
            return ["127.0.0.1"]

        items = [x.strip() for x in target_spec.split(",") if x.strip()]
        result_ips: List[str] = []

        for item in items:
            # Check Range: e.g. "10.1.7.50-10.1.7.54" or "10.1.7.50 - 10.1.7.54"
            if "-" in item and not item.startswith("-"):
                parts = item.split("-", 1)
                start_str = parts[0].strip()
                end_str = parts[1].strip()
                try:
                    start_ip = ipaddress.IPv4Address(start_str)
                    # If end part is just the last octet (e.g. 10.1.7.50-60)
                    if "." not in end_str and end_str.isdigit():
                        prefix = start_str.rsplit(".", 1)[0]
                        end_ip = ipaddress.IPv4Address(f"{prefix}.{end_str}")
                    else:
                        end_ip = ipaddress.IPv4Address(end_str)

                    start_int = int(start_ip)
                    end_int = int(end_ip)
                    if start_int <= end_int:
                        for ip_int in range(start_int, end_int + 1):
                            if len(result_ips) >= max_hosts:
                                break
                            result_ips.append(str(ipaddress.IPv4Address(ip_int)))
                        continue
                except Exception:
                    pass

            # Check CIDR: e.g. "10.1.7.0/24"
            if "/" in item:
                try:
                    net = ipaddress.IPv4Network(item, strict=False)
                    # If single IP (/32)
                    if net.num_addresses == 1:
                        result_ips.append(str(net.network_address))
                    elif net.num_addresses == 2:
                        for h in net:
                            result_ips.append(str(h))
                    else:
                        for h in net.hosts():
                            if len(result_ips) >= max_hosts:
                                break
                            result_ips.append(str(h))
                    continue
                except Exception:
                    pass

            # Check Hostname or Single IP: e.g. "Jamese-PC" or "10.1.7.74"
            try:
                ip_obj = ipaddress.IPv4Address(item)
                result_ips.append(str(ip_obj))
            except Exception:
                # Try name resolution
                try:
                    resolved_ip = socket.gethostbyname(item)
                    result_ips.append(resolved_ip)
                except Exception:
                    result_ips.append(item)

        # De-duplicate while preserving order
        seen = set()
        deduped = []
        for ip in result_ips:
            if ip not in seen:
                seen.add(ip)
                deduped.append(ip)
            if len(deduped) >= max_hosts:
                break

        return deduped

    def resolve_host_alias(self, ip: str) -> str:
        """
        Resolves reverse DNS / NetBIOS hostname alias for an IP address.
        Uses in-memory cache to prevent repeated reverse-DNS latency.
        """
        if ip in self._alias_cache:
            return self._alias_cache[ip]

        if ip in ["127.0.0.1", "localhost", "::1"]:
            alias = socket.gethostname() or "localhost"
            self._alias_cache[ip] = alias
            return alias

        alias = ip
        try:
            name, _, _ = socket.gethostbyaddr(ip)
            if name:
                alias = name.split(".")[0]  # Short computer name
        except Exception:
            alias = ip

        self._alias_cache[ip] = alias
        return alias

    def build_scan_targets(
        self,
        ips: List[str],
        platforms: Optional[List[str]] = None,
        secondary_ports: Optional[List[int]] = None
    ) -> List[Tuple[str, int]]:
        """
        Generates (ip, port) pairs from the selected platforms and secondary ports.
        """
        ports_to_scan: List[int] = []

        if platforms:
            for p in platforms:
                p_key = p.lower().strip()
                if p_key in PLATFORM_CATALOG:
                    cfg = PLATFORM_CATALOG[p_key]
                    if cfg["port"] not in ports_to_scan:
                        ports_to_scan.append(cfg["port"])
                    for sp in cfg.get("secondary_ports", []):
                        if sp not in ports_to_scan:
                            ports_to_scan.append(sp)
        else:
            ports_to_scan = list(STANDARD_AI_PORTS)

        if secondary_ports:
            for sp in secondary_ports:
                if sp not in ports_to_scan:
                    ports_to_scan.append(int(sp))

        targets: List[Tuple[str, int]] = []
        for ip in ips:
            for p in ports_to_scan:
                targets.append((ip, p))

        return targets

    def classify_device(self, candidate_info: Dict[str, Any]) -> str:
        """
        Categorizes device into one of three visual states:
        - 'KNOWN_SERVICES' (Bright Turquoise): Confirmed active AI engine with models.
        - 'NO_SERVICES' (Red): Host reachable/responsive on network, but no AI services open.
        - 'PENDING' (Orange): Unprobed, queued, or unknown response.
        """
        if candidate_info.get("engine") and candidate_info.get("port"):
            return "KNOWN_SERVICES"
        if candidate_info.get("host_responsive") is True:
            return "NO_SERVICES"
        return "PENDING"

    def probe_host(self, ip: str, port: int, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Tests if target port is open and conducts safe HTTP JSON fingerprinting.
        Returns candidate details dictionary or None if closed/non-AI.
        """
        t_out = timeout or self.default_timeout
        t_start = time.time()

        # 1. Fast socket connectivity check
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(t_out)
            res = s.connect_ex((ip, port))
            s.close()
            if res != 0:
                return None
        except Exception:
            return None

        connect_latency = (time.time() - t_start) * 1000.0
        alias = self.resolve_host_alias(ip)

        # 2. HTTP fingerprinting
        endpoint = f"http://{ip}:{port}"

        # Attempt A: Ollama /api/version
        try:
            req = urllib.request.Request(f"{endpoint}/api/version")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    ver_data = json.loads(resp.read().decode("utf-8"))
                    version_str = ver_data.get("version", "unknown")

                    models_list = []
                    try:
                        req_tags = urllib.request.Request(f"{endpoint}/api/tags")
                        with urllib.request.urlopen(req_tags, timeout=1.0) as resp_tags:
                            tags_data = json.loads(resp_tags.read().decode("utf-8"))
                            models_list = tags_data.get("models", [])
                    except Exception:
                        pass

                    return {
                        "ip": ip,
                        "alias": alias,
                        "port": port,
                        "endpoint": endpoint,
                        "engine": "ollama",
                        "version": version_str,
                        "models": models_list,
                        "latency_ms": round(connect_latency, 1),
                        "discovered_at": time.time(),
                        "state": "KNOWN_SERVICES"
                    }
        except Exception:
            pass

        # Attempt B: OpenAI / vLLM / LM Studio /v1/models
        for path in ["/v1/models", "/models"]:
            try:
                req = urllib.request.Request(f"{endpoint}{path}")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        m_data = json.loads(resp.read().decode("utf-8"))
                        raw_models = m_data.get("data", [])
                        models_list = []
                        engine_name = "openai_compatible"
                        for m in raw_models:
                            m_id = m.get("id") if isinstance(m, dict) else str(m)
                            owned_by = m.get("owned_by", "") if isinstance(m, dict) else ""
                            if "vllm" in owned_by.lower():
                                engine_name = "vllm"
                            models_list.append({"name": m_id, "details": {"owned_by": owned_by}})

                        if port == 1234:
                            engine_name = "lmstudio"

                        return {
                            "ip": ip,
                            "alias": alias,
                            "port": port,
                            "endpoint": endpoint,
                            "engine": engine_name,
                            "version": "v1",
                            "models": models_list,
                            "latency_ms": round(connect_latency, 1),
                            "discovered_at": time.time(),
                            "state": "KNOWN_SERVICES"
                        }
            except Exception:
                pass

        return None

    def scan_targets(self, targets: List[Any], timeout: Optional[float] = None, max_workers: int = 30) -> List[Dict[str, Any]]:
        """
        Scans a list of target tuples (ip, port) or strings 'ip:port' using concurrent workers.
        """
        normalized: List[Tuple[str, int]] = []
        for t in targets:
            if isinstance(t, tuple) and len(t) == 2:
                normalized.append((str(t[0]), int(t[1])))
            elif isinstance(t, str):
                parts = t.split(":")
                if len(parts) == 2:
                    normalized.append((parts[0].strip(), int(parts[1].strip())))

        candidates: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_target = {
                executor.submit(self.probe_host, ip, port, timeout): (ip, port)
                for ip, port in normalized
            }
            for future in as_completed(future_to_target):
                try:
                    res = future.result()
                    if res:
                        candidates.append(res)
                except Exception:
                    pass

        # Sort by latency
        candidates.sort(key=lambda x: x.get("latency_ms", 9999.0))
        return candidates

    def scan_local_subnet(
        self,
        subnet_cidr: Optional[str] = None,
        ports: Optional[List[int]] = None,
        timeout: Optional[float] = None,
        max_workers: int = 35
    ) -> List[Dict[str, Any]]:
        """
        Sweeps standard AI ports across the local /24 subnet or specified CIDR/spec.
        """
        host_ip, detected_subnet = self.get_local_subnet_info()
        target_spec = subnet_cidr or detected_subnet
        ips = self.parse_target_spec(target_spec)

        # Ensure localhost is included
        if "127.0.0.1" not in ips:
            ips.append("127.0.0.1")

        scan_ports = ports or STANDARD_AI_PORTS
        targets: List[Tuple[str, int]] = []
        for ip in ips:
            for p in scan_ports:
                targets.append((ip, p))

        return self.scan_targets(targets, timeout=timeout, max_workers=max_workers)
