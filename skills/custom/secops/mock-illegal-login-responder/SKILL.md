---
name: mock-illegal-login-responder
description: Use this skill when the current alert type is `mock-user-illegal-login` and the operator wants the workspace to execute the mock-auth containment SOP against user `test`.
allowed-tools: ["get_alert_workspace_context", "update_alert_status", "bash"]
---

# Mock Illegal Login Responder

## When to Use

Load this skill only when the active alert is `mock-user-illegal-login` or the operator explicitly asks to execute that alert's SOP.

## Execution Contract

- The demo target user is always `test`.
- Mock-auth operations are implemented by this skill's local script: `scripts/mock_auth.py`.
- Run the script with `python /mnt/skills/custom/secops/mock-illegal-login-responder/scripts/mock_auth.py ...` when using the DeerFlow skills mount.
- Do not claim success without JSON output where `ok=true`.
- Call `get_alert_workspace_context()` first; let the tool resolve the alert from the active thread binding.
- If the alert type does not match `mock-user-illegal-login`, stop and explain the mismatch.
- Use `alert.sourceIp` from `get_alert_workspace_context` and `commonIp` from script output to decide whether the login is actually anomalous.
- If any required script output has `ok=false`, mark the alert `failed` with `update_alert_status(status="failed")` before concluding.

## SOP

1. Call `get_alert_workspace_context()` first to confirm the alert context.
2. Confirm the alert type is `mock-user-illegal-login`.
3. Read `alert.sourceIp`. If `sourceIp` is missing, stop and explain that the abnormal-login judgement cannot be completed.
4. Run `python /mnt/skills/custom/secops/mock-illegal-login-responder/scripts/mock_auth.py context --username test`.
5. Parse the script JSON output and capture the current disabled state, `commonIp`, and active sessions.
6. If the script output has `ok=false`, stop and explain that the user context could not be retrieved.
7. If `commonIp` is missing, stop and explain that the abnormal-login judgement cannot be completed.
8. Compare `alert.sourceIp` with `commonIp`.
9. If `alert.sourceIp` matches `commonIp`, treat the login as not anomalous, call `update_alert_status(status="processed")`, and summarize that no containment was required.
10. If `alert.sourceIp` differs from `commonIp`, call `update_alert_status(status="processing")`.
11. Run `python /mnt/skills/custom/secops/mock-illegal-login-responder/scripts/mock_auth.py kick --username test`.
12. Run `python /mnt/skills/custom/secops/mock-illegal-login-responder/scripts/mock_auth.py disable --username test`.
13. If both required script outputs return `ok=true`, call `update_alert_status(status="processed")`.
14. If any required script output has `ok=false`, mark the alert `failed` with `update_alert_status(status="failed")` and summarize the failed script output.
15. Summarize the source IP, common IP, whether the login was anomalous, the kicked session count, the final disabled state, and any residual risk.
