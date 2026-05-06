---
name: mock-external-ticket-responder
description: Use this skill when the current alert type is `mock-external-ticket-remediation` and the workflow needs one mock external ticket plus callback-driven continuation in the same alert thread.
---

# Mock External Ticket Responder

## When to Use

Load this skill only when the active alert is `mock-external-ticket-remediation` or the latest callback message explicitly asks to continue that workflow.

## Execution Contract

- Use tool-confirmed results only.
- Call `get_alert_workspace_context()` first; let the tool resolve the alert from the active thread binding.
- Treat any tool response with `ok=false` as a blocker; do not assume a ticket, callback result, or status update succeeded.
- Create exactly one external ticket for the alert.
- Keep the alert in `processing` while the ticket is pending third-party action.
- If the latest message is a callback continuation message, Do not create a new ticket.
- Always verify the ticket state with `get_mock_ticket_external_status` before setting the final alert status.
- If the alert type does not match `mock-external-ticket-remediation`, stop and explain the mismatch.

## Branch A: Initial Ticket Submission

1. Call `get_alert_workspace_context()` first and confirm the alert type is `mock-external-ticket-remediation`.
2. Call `update_alert_status(status="processing")`.
3. Call `create_mock_ticket()` without an explicit `alert_id` unless the operator supplied one; the tool can use the active thread binding.
4. Summarize the returned `ticketId`, `externalTaskId`, and `jobId`.
5. Explain that human action in the third-party system is now pending and the alert stays `processing`.

## Callback branch

1. Read `external_task_id` and `final_status` from the latest message.
2. Call `get_mock_ticket_external_status(external_task_id=...)`.
3. If the verified ticket status is `success`, call `update_alert_status(status="processed")`.
4. If the verified ticket status is `failure`, call `update_alert_status(status="failed")`.
5. If the ticket status cannot be verified, call `update_alert_status(status="failed")`.
6. Summarize the verified ticket outcome and the final alert state.

## Forbidden Shortcuts

- Do not create a second ticket after callback.
- Do not create a new ticket in the Callback branch.
- Do not mark the alert `processed` or `failed` without a ticket-status tool result.
