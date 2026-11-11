# Feature Recipe FR-906: Responsive Non-Stretching SVG Engine, Chart Timeline Synchronization & Model Sparkline Population

## 1. Specification (ASD-STE100 Simplified Technical English)
- **Problem**:
  1. SVG charts on wide and ultrawide viewports stretch non-uniformly because fixed `viewBox="0 0 900 200"` and `preserveAspectRatio="none"` are used. Data dots deform into horizontal ovals, line strokes distort non-uniformly, and text fonts stretch horizontally.
  2. Hierarchical trend curves in the Web UI stop updating while Token Velocity and Mini Widget curves continue. Clicking "Refresh" or "Sync Now" does not update plots because client-side `cachedHierarchicalTrends` is not invalidated.
  3. Ollama model cards display empty sparklines (`0 t (idle)`) even when models have significant token usage (e.g., `nomic-embed-text:latest` and `gemma:2b`), due to identifier mismatch (`ollama_model_...` vs colons `:`) and lack of asynchronous sparkline updating when trend data arrives.
  4. Claude "Individual Member" and "Team Workspace" cards display identical 1:1 plots because personal Claude Pro events are added to both individual and team buckets.
- **Solution**:
  1. Build a unified responsive SVG rendering engine measuring actual container pixel width (`clientWidth`), removing `preserveAspectRatio="none"`, computing coordinates 1:1 with screen pixels, using `vector-effect="non-scaling-stroke"`, and attaching a debounced ResizeObserver.
  2. Invalidate `cachedHierarchicalTrends` on every manual refresh, auto-refresh poll, and provider sync.
  3. Normalize model identifier matching in `getChildRealPoints`, add dedicated DOM identifiers for model sparkline containers, and update child sparklines immediately when trend data loads.
  4. Disaggregate Claude personal Pro usage from team workspace pool so team curves reflect team workspace metrics rather than duplicating personal turns 1:1.

## 2. Architecture Decisions
- Container-relative pixel coordinate calculation: `width = Math.max(container.clientWidth, 400)`.
- Removal of `preserveAspectRatio="none"`; viewBox matches exact measured pixel width and height.
- Dynamic element resize listener via `ResizeObserver` with 60ms debounce.
- Asynchronous child sparkline dispatch: `updateChildSparklines(providerKey, data)`.
- Backend separation of `personal_pro` account tier from `team_org` workspace pool in `get_hierarchical_trends`.

## 3. Test Assertions
1. `test_token_velocity_chart_no_preserve_aspect_ratio_none`: Verify `preserveAspectRatio="none"` is eliminated from `usage_gauge_card.html` and `app.js`.
2. `test_render_svg_chart_measures_container_width`: Verify `renderSvgChart` measures container width dynamically rather than hardcoding 900.
3. `test_render_hierarchical_chart_measures_container_width`: Verify `renderMultiSeriesTrendChart` measures container width dynamically.
4. `test_sparklines_use_vector_effect_non_scaling_stroke`: Verify sparklines use `vector-effect="non-scaling-stroke"`.
5. `test_cached_hierarchical_trends_cleared_on_load_usage_data`: Verify `loadUsageData` clears `cachedHierarchicalTrends`.
6. `test_cached_hierarchical_trends_cleared_on_sync_provider`: Verify `syncProvider` clears `cachedHierarchicalTrends`.
7. `test_get_child_real_points_normalizes_colons_and_underscores`: Verify `getChildRealPoints` matches model IDs with colons and underscores.
8. `test_ollama_model_cards_render_sparklines_when_tokens_exist`: Verify model cards populate with non-zero points when data is available.
9. `test_update_child_sparklines_updates_dom_elements`: Verify `updateChildSparklines` updates child sparkline containers in DOM.
10. `test_claude_individual_and_team_disaggregated_in_trends`: Verify `get_hierarchical_trends` produces distinct series for individual vs team workspace.
11. `test_claude_personal_events_not_added_to_team_org`: Verify personal events are strictly attributed to individual.
12. `test_hierarchical_trends_keys_and_labels_match_current_time`: Verify latest bin aligns with local system hour.
13. `test_resize_observer_wires_chart_re_render`: Verify resize handling re-renders charts without page refresh.
14. `test_widget_and_web_ui_share_window_selection`: Verify window sync between widget and web UI.
15. `test_zero_activity_models_display_idle_sparkline`: Verify models with 0 tokens display clean idle indicator.
16. `test_active_models_display_correct_polyline_points`: Verify models with tokens display colored polyline.
17. `test_chart_dot_radius_is_uniform_across_screen_widths`: Verify dot elements use circular radius.
18. `test_text_labels_not_stretched`: Verify text element typography is un-distorted.
19. `test_single_provider_notice_responsive`: Verify single-provider notice adapts to width.
20. `test_end_to_end_chart_rendering_pipeline`: Verify end-to-end flow from backend query to frontend DOM output.
