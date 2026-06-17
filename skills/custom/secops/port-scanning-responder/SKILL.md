---
name: port-scanning-responder
description: Use this skill when the current alert type is `port-scanning` or `Port scanning`. Treats all port scanning alerts as false positives and completes them with an agent-generated report.
allowed-tools: ["get_alert_workspace_context", "update_alert_status", "complete_alert_with_report"]
---

# Port Scanning Responder

## When to Use

Load this skill only when the active alert type is `port-scanning` or `Port scanning`.

## Execution Contract

- All port scanning alerts are treated as false positives by default.
- No investigation or containment action is required.
- The alert must be completed as `processed` with an agent-generated report.
- Call `get_alert_workspace_context()` first; let the tool resolve the alert from the active thread binding.
- Do not claim the alert was processed unless report-backed completion returns `ok=true`.

## SOP

1. Call `get_alert_workspace_context()` first to confirm the alert context.
2. If the tool returns `ok=false`, stop and explain that the active alert could not be resolved from the thread.
3. Confirm the alert type is `port-scanning` or `Port scanning`. If not, stop and explain the mismatch.
4. Generate a Markdown report with alert summary, investigation basis, reason no containment was required, final result, residual risk, and follow-up recommendations.
5. Call `complete_alert_with_report(status="processed", title="Port scanning alert processed", summary="The port scanning alert was classified as a false positive.", content_markdown=<generated_report>)`.
6. If report-backed completion returns `ok=false`, stop and report that the alert report and final status could not be saved.
7. Summarize that the port scanning alert has been classified as a false positive and marked as processed without further action.
