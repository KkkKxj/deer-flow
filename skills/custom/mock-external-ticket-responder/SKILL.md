---
name: mock-external-ticket-responder
description: Use this skill when the current alert type is `mock-external-ticket-remediation` and the workflow needs one mock external ticket plus callback-driven continuation in the same alert thread.
---

# Mock External Ticket Responder

## When to Use

Load this skill only when the active alert is `mock-external-ticket-remediation` or the latest callback message explicitly asks to continue that workflow.

## Execution Contract

- Mock-ticket operations are implemented by this skill's local script: `scripts/mock_ticket.py`.
- Run the script with `python /mnt/skills/custom/mock-external-ticket-responder/scripts/mock_ticket.py ...` when using the DeerFlow skills mount.
- Use tool-confirmed and script-confirmed results only.
- Call `get_alert_workspace_context()` first; let the tool resolve the alert from the active thread binding.
- Treat any tool response or script output with `ok=false` as a blocker; do not assume a ticket, callback result, or status update succeeded.
- Create exactly one external ticket for the alert.
- Keep the alert in `processing` while the ticket is pending third-party action.
- If the latest message is a callback continuation message, do not create a new ticket.
- Always verify the ticket state with `scripts/mock_ticket.py status --external-task-id ...` before completing the alert with a report.
- If the alert type does not match `mock-external-ticket-remediation`, stop and explain the mismatch.

## Branch A: Initial Ticket Submission

1. Call `get_alert_workspace_context()` first and confirm the alert type is `mock-external-ticket-remediation`.
2. Capture `alert.id` as `alert_id`.
3. Capture the active thread id from the workspace context output or the current run context as `thread_id`. If no `thread_id` is available, stop and explain that callback continuation requires the original alert thread id.
4. Call `update_alert_status(status="processing")`.
5. Run `python /mnt/skills/custom/mock-external-ticket-responder/scripts/mock_ticket.py create --alert-id <alert_id> --thread-id <thread_id> --alert-type mock-external-ticket-remediation --agent-name secops-agent`.
6. Parse the script JSON output.
7. If the script output has `ok=false`, generate a failure report and call `complete_alert_with_report(status="failed", title="External ticket creation failed", summary="The mock external ticket could not be created.", content_markdown=<generated_report>)`.
8. Summarize the returned `ticketId`, `externalTaskId`, and `jobId`.
9. Explain that human action in the third-party system is now pending and the alert stays `processing`.

## Callback branch

1. Read `external_task_id` and `final_status` from the latest message.
2. Run `python /mnt/skills/custom/mock-external-ticket-responder/scripts/mock_ticket.py status --external-task-id <external_task_id>`.
3. Parse the script JSON output.
4. If the script output has `ok=false`, generate a failure report and call `complete_alert_with_report(status="failed", title="External ticket verification failed", summary="The external ticket status could not be verified.", content_markdown=<generated_report>)`.
5. If the verified ticket status is `success`, generate a report and call `complete_alert_with_report(status="processed", title="External ticket remediation completed", summary="The external ticket completed successfully and the alert was verified.", content_markdown=<generated_report>)`.
6. If the verified ticket status is `failure`, generate a report and call `complete_alert_with_report(status="failed", title="External ticket remediation failed", summary="The external ticket reported failure.", content_markdown=<generated_report>)`.
7. If the ticket status cannot be verified, generate a failure report and call `complete_alert_with_report(status="failed", title="External ticket status unknown", summary="The external ticket status could not be verified.", content_markdown=<generated_report>)`.
8. Summarize the verified ticket outcome and the final alert state.

## Forbidden Shortcuts

- Do not create a second ticket after callback.
- Do not create a new ticket in the Callback branch.
- Do not mark the alert `processed` or `failed` without a ticket-status script result and report-backed completion.
