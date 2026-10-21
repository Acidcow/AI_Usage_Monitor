# Feature Recipe FR-704: Configurable LAN Discovery, Alias-Based Device Inventory, Ambient Scanning, Trusted Compute Groups & Query Console

## 1. Goal
Enhance the LAN discovery system with user-configurable IP ranges and CIDR subnets, presets, guidance tooltips, and persistent alias-keyed device inventories. Provide platform checkboxes and secondary port scanning. Color-code discovered devices by service status (turquoise for known AI services, red for alive with no AI services, orange for pending/unknown). Introduce trust levels and compute groups for nodes (untrusted devices excluded from active compute). Implement an interactive query and prompt console with file attachment context support, failover pool routing, and prominent security warnings when untrusted resources are targeted.

## 2. Technical Requirements

### 1. Advanced LAN & Subnet Scanner (`backend/discovery/lan_scanner.py`)
- **Multi-Adapter & Subnet Detection**: Detect all active IPv4 interfaces and derived subnets using standard library socket calls and Windows network inspection.
- **Flexible Target Parsing**:
  - CIDR notation (e.g. `10.1.7.0/24`, `192.168.1.0/28`).
  - IP Ranges (e.g. `10.1.7.1-10.1.7.100`).
  - Hostnames & Aliases (e.g. `Jamese-PC`, `ASUS-ROG`, `localhost`).
  - Comma-separated hybrid lists (`10.1.7.74, 127.0.0.1, Jamese-PC`).
- **Safety Clamps**: Enforce a maximum host sweep ceiling (1024 hosts default) to prevent network storms when wide masks (e.g. `/16`) are specified.
- **Hostname / Alias Resolution**:
  - Perform reverse DNS (`socket.gethostbyaddr(ip)`) to resolve hostnames.
  - Fallback to NetBIOS or ARP lookup to correlate dynamic IPs with consistent computer aliases.
- **Platform & Port Selection**:
  - Modular platform catalog with target ports, paths, and fingerprinting probes:
    - Ollama (11434)
    - LM Studio (1234)
    - vLLM / LocalAI / LiteLLM (8000, 8080)
    - Text Generation WebUI (5000)
    - Tabby / KoboldCPP (5001, 8081)
    - Open WebUI (3000)
  - Configurable secondary ports and user-defined custom ports.
- **Host State Classification**:
  - `KNOWN_SERVICES`: Port open, valid AI engine HTTP fingerprint matched.
  - `NO_SERVICES`: Host reachable/socket responsive, but no AI services discovered.
  - `PENDING`: Unprobed or queued candidate.

### 2. Persistent Device Inventory & Compute Groups (`backend/storage/database.py`)
- **`device_inventory` Table**:
  - `id`: Unique identifier (e.g. `dev_jamese_pc` or `dev_10_1_7_74`)
  - `alias`: Primary host reference (e.g. `Jamese-PC`, `ASUS-ROG`)
  - `ip`: Last seen IPv4 address
  - `state`: `KNOWN_SERVICES`, `NO_SERVICES`, `PENDING`
  - `discovered_services_json`: Serialized catalog of discovered endpoints, engines, models
  - `is_trusted`: Boolean (1 for trusted, 0 for untrusted)
  - `compute_group`: String (`Active Compute`, `Staging / Evaluation`, `Quarantined`, or custom)
  - `first_seen_at`, `last_seen_at`: ISO8601 timestamps
- **`managed_nodes` Table Updates**:
  - Add `is_trusted` (integer 1/0, default 1).
  - Add `compute_group` (text, default `'Active Compute'`).
  - Strict rule: If `is_trusted == 0`, node is automatically excluded from `'Active Compute'`.

### 3. Pool Routing with Trust Prioritization & Failover (`backend/discovery/traffic_governor.py`)
- **Pool Target Dispatch**:
  - When `node_id="pool"` or `node_id="active_compute"`, filter nodes matching `compute_group == 'Active Compute'` and `is_trusted == 1`.
  - Order candidates by `priority DESC, latency_ms ASC`.
  - Failover mechanism: If the highest priority node trips circuit breaker or errors, seamlessly failover to the next trusted candidate.
  - Untrusted nodes are strictly excluded from automated pool routing.

### 4. REST API Endpoints (`backend/server/http_server.py`)
- `GET /api/discovery/adapters`: Returns detected network adapters, active IPs, and derived subnets.
- `GET /api/discovery/inventory`: Returns persistent device inventory with status color tags and aliases.
- `POST /api/discovery/inventory`: Upsert or edit device alias, trust status, and compute group.
- `DELETE /api/discovery/inventory`: Remove device from inventory.
- `POST /api/discovery/scan`: Enhanced sweep accepting `preset`, `cidr_range`, `platforms`, and `secondary_ports`.
- `POST /api/discovery/query`: Interactive prompt console endpoint accepting prompt, file context attachments, target node or pool, and returning token telemetry.

### 5. Frontend UI Extensions (`frontend/components/provider_hub.html` & `frontend/js/app.js`)
- **Subnet Configuration & Presets**:
  - Preset dropdown (`Auto-detected`, `Class C 192.168.1.0/24`, `Class C 192.168.0.0/24`, `Class A 10.1.7.0/24`, `Custom Range`).
  - Guidance info-card explaining subnet masks (`/24`, `/28`, `/16`), scan times, and firewall setup (`OLLAMA_HOST=0.0.0.0`).
- **Platform Checkboxes & Tooltips**:
  - Interactive checkboxes with tooltips detailing default ports, endpoints, and caveats.
- **3-Color Device Status Inventory**:
  - Bright Turquoise (`#06b6d4` / `#22d3ee`): Known AI Services.
  - Red (`#ef4444` / `#f87171`): Host alive, NO AI services.
  - Orange (`#f59e0b` / `#fbbf24`): Pending / Unscanned.
- **Trust & Group Allocation Controls**:
  - Toggle node trust (Trusted vs Untrusted).
  - Assign to compute groups or create new groups.
  - Visual red badges for untrusted resources.
- **Interactive Query & Prompt Console**:
  - Target selection (`Active Compute Pool` or specific node).
  - File context uploader (drag & drop / multi-file read).
  - Prominent RED warning modal/banner when untrusted nodes are targeted with file attachments.
  - Real-time token output, latency, TTFT, and telemetry ingest display.

## 3. Verification Criteria
- [ ] IP range parser correctly resolves CIDRs, ranges (`10.1.7.1-10.1.7.50`), and aliases.
- [ ] Hostname resolver correlates dynamic IPs with persistent aliases.
- [ ] Device inventory table persists across reboots with 3 distinct color states.
- [ ] Untrusted nodes are strictly blocked from the `Active Compute` pool and failover.
- [ ] Query console successfully dispatches prompts with attached file context and records token telemetry.
- [ ] Full test suite (>=20 new tests) passes with 100% green execution.
