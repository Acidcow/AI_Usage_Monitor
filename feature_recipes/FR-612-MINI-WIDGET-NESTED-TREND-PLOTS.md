# Feature Recipe FR-612: Mini Widget Multi-Plot Overlays, Nested Branch Charts & Parent Visibility Toggle

## 1. Goal
Upgrade the Mini Widget's trend (line-chart) view so top-level platform cards overlay individual line plots corresponding to each child entity (e.g. Gemini account + individual API keys, Claude team + individual). Enable nested branch charts upon expanding child sections with consistent color coding, color swatch blocks left of headers, and a configuration toggle to either hide the parent chart or keep it visible as child nodes expand.

## 2. Technical Requirements
1. **Top-Level Overlaid Line Plots**:
   - In widget trend mode, render a composite canvas / SVG chart that overlays line plots for the parent and all child nodes.
   - Example (Gemini): Main plot line for `acidcow@gmail.com` account plus distinct colored lines for each child API key.
   - Example (Claude): Distinct colored lines for Team Pool and Individual Member quota consumption.

2. **Nested Branch Charts on Node Expansion**:
   - When expanding a child branch in the trend analysis view, display dedicated child charts for each subsequent branch.
   - Render each line in its assigned color.
   - Render a small colored swatch block (`■`) directly to the left of each item name/header to indicate its plot line color.

3. **Parent Chart Visibility Configuration**:
   - Provide a configuration toggle: `widget_hide_parent_chart_on_expand` (boolean, default: `false`).
   - When `true`: expanding child nodes collapses or hides the top-level parent chart to save vertical screen space.
   - When `false`: both the top-level composite chart and the nested child charts remain visible simultaneously.

4. **Synchronized Support Across Mini Widget Implementations**:
   - Support both the Web Mini Widget (`frontend/mini_widget.html`, `frontend/js/widget.js`) and the Native Win32/Tkinter Taskbar Widget (`backend/tray/native_widget.py`).

## 3. Verification Criteria
- [x] Top-level widget trend view displays multi-line overlaid plots.
- [x] Expanding an item displays child branch line charts with assigned colors.
- [x] Color swatch block is rendered adjacent to item headers.
- [x] Configuration toggle `widget_hide_parent_chart_on_expand` successfully hides or preserves the parent chart.
- [x] Both web widget and native widget render correctly without crashes or UI clipping.

