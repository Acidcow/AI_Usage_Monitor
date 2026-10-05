# Feature Recipe FR-206: Dashboard Real Data Mode & Live SVG Analytics Chart

## 1. Goal
Provide clear toggle between "Real Local Data" and "Demo Simulation", and an interactive, pure SVG time-series analytics chart with zero external dependencies.

## 2. Technical Requirements
1. **Mode Switch**:
   - Header badge displaying: `🟢 LIVE DATA (Auto-Scanned)` vs `🟡 DEMO SIMULATION`.
   - Toggle switch in UI to enable or disable simulation mode.
2. **Pure SVG Analytics Chart**:
   - Renders 24-hour and 7-day token consumption trends using inline SVG vectors (path, area fill, axes, hover tooltips).
   - Zero external libraries (no Chart.js, D3, or npm modules).
3. **Real-time Ollama Model Table**:
   - Displays all local models detected with parameter size, quantization level, and family badges.

## 3. Verification Criteria
- SVG chart scales responsively without visual distortion.
- Switching between real and demo modes refreshes charts immediately.
