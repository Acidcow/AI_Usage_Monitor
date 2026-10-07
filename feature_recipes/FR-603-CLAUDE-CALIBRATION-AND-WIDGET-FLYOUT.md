# Feature Recipe FR-603: Claude Team Quota Calibration, Widget Auto-Port Probing & Scaled Hover Flyout

## 1. Goal
Resolve discrepancies between Claude official web UI metrics and AI Usage Monitor dashboard, fix widget pop-out port routing, eliminate test-spawned orphan widget processes, and scale native widget hover flyout panels to prevent text truncation.

## 2. Technical Requirements
1. **Claude Rolling Quota Calibration & Team Limits Support**:
   - Claude web interface measures usage via rolling session % (e.g. 56% used = 44% remaining) and weekly all-models pool % (e.g. 26% used = 74% remaining).
   - Add database persistence and migration for `session_remaining_pct`, `weekly_remaining_pct`, and `weekly_reset_str` in `provider_snapshots`.
   - Update `UsageDatabase.get_comparative_metrics()` to honor explicit calibrated snapshot percentages when present.
   - Implement `ClaudeProvider.calibrate_limits()` and REST API endpoint `POST /api/providers/claude/quota`.
   - Provide a UI calibration modal in the Web Dashboard so users can align session and weekly limits with `claude.ai` in two clicks.
   - Pre-seed realistic Team Enterprise quota defaults matching user's active workspace.

2. **Native Widget Active Port Probing & Pop-out Routing**:
   - In `NativeTaskbarWidget`, dynamically probe `self.active_port`, fallback to `8765`, and update `self.active_port` upon successful connection.
   - Update `_open_browser` to launch `http://{self.host}:{self.active_port}/`, ensuring the pop-out arrow `↗` never opens dead ephemeral ports.
   - Update `port_lbl` to reflect the active connected port.
   - In `launch_desktop_widget`, add `dry_run` support and ensure unit tests pass `dry_run=True` to prevent spawning orphan GUI windows on ephemeral test ports.

3. **Scaled Native Hover Flyout Panel**:
   - Scale hover flyout width to match the mini widget width (370px).
   - Double vertical space to ~210px (was 100px) to prevent text clipping at all Windows DPI scaling levels.
   - Align horizontal coordinate `wx` with the widget's left edge (`self.root.winfo_rootx()`).
   - Implement vertical scrolling support with a sleek, minimal 4px scrollbar.
   - Display formatted details: Provider name, plan badge, session quota remaining/used, session reset countdown, weekly quota remaining/used, weekly reset schedule, today's tokens, weekly volume, and estimated cost.

## 3. Verification Criteria
- Automated tests pass with 100% success rate:
  - `test_claude_calibrate_limits` in `tests/test_claude_provider.py`.
  - `test_api_claude_quota_calibration` in `tests/test_http_api.py`.
  - `test_api_widget_launch_dry_run` in `tests/test_http_api.py`.
  - `test_native_taskbar_widget_flyout_geometry_and_port_probing` in `tests/test_windows_tray.py`.
- Zero external dependencies (Python Standard Library only).
