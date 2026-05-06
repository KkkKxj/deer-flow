---
name: port-scanning-responder
description: Use this skill when the current alert type is `port-scanning` or `Port scanning`. Treats all port scanning alerts as false positives and marks them as processed without further action.
---

# Port Scanning Responder

## When to Use

Load this skill only when the active alert type is `port-scanning` or `Port scanning`.

## Execution Contract

- All port scanning alerts are treated as false positives by default.
- No investigation or containment action is required.
- The alert must be marked as `processed` immediately.
- Call `get_alert_workspace_context()` first; let the tool resolve the alert from the active thread binding.
- Do not claim the alert was processed unless the status update returns `ok=true`.

## SOP

1. Call `get_alert_workspace_context()` first to confirm the alert context.
2. If the tool returns `ok=false`, stop and explain that the active alert could not be resolved from the thread.
3. Confirm the alert type is `port-scanning` or `Port scanning`. If not, stop and explain the mismatch.
4. Call `update_alert_status(status="processed")`.
5. If the status update returns `ok=false`, stop and report that the alert status could not be updated.
6. Summarize that the port scanning alert has been classified as a false positive and marked as processed without further action.
