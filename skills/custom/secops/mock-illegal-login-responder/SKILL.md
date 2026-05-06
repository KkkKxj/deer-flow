---
name: mock-illegal-login-responder
description: Use this skill when the current alert type is `mock-user-illegal-login` and the operator wants the workspace to execute the mock-auth containment SOP against user `test`.
---

# Mock Illegal Login Responder

## When to Use

Load this skill only when the active alert is `mock-user-illegal-login` or the operator explicitly asks to execute that alert's SOP.

## Execution Contract

- The demo target user is always `test`.
- Do not claim success without tool-confirmed outputs.
- Call `get_alert_workspace_context()` first; let the tool resolve the alert from the active thread binding.
- If the alert type does not match `mock-user-illegal-login`, stop and explain the mismatch.
- Use `alert.sourceIp` from `get_alert_workspace_context` and `commonIp` from `get_mock_auth_user_context` to decide whether the login is actually anomalous.
- If any required remediation tool returns `ok=false`, mark the alert `failed` with `update_alert_status(status="failed")` before concluding.

## SOP

1. Call `get_alert_workspace_context()` first to confirm the alert context.
2. Confirm the alert type is `mock-user-illegal-login`.
3. Read `alert.sourceIp`. If `sourceIp` is missing, stop and explain that the abnormal-login judgement cannot be completed.
4. Call `get_mock_auth_user_context(username="test")` and capture the current disabled state, `commonIp`, and active sessions.
5. If the user-context tool returns `ok=false`, stop and explain that the user context could not be retrieved.
6. If `commonIp` is missing, stop and explain that the abnormal-login judgement cannot be completed.
7. Compare `alert.sourceIp` with `commonIp`.
8. If `alert.sourceIp` matches `commonIp`, treat the login as not anomalous, call `update_alert_status(status="processed")`, and summarize that no containment was required.
9. If `alert.sourceIp` differs from `commonIp`, call `update_alert_status(status="processing")`.
10. Call `kick_mock_auth_user_sessions(username="test")`.
11. Call `disable_mock_auth_user(username="test")`.
12. If both required actions return `ok=true`, call `update_alert_status(status="processed")`.
13. If any required remediation tool returns `ok=false`, mark the alert `failed` with `update_alert_status(status="failed")` and summarize the failed tool output.
14. Summarize the source IP, common IP, whether the login was anomalous, the kicked session count, the final disabled state, and any residual risk.
