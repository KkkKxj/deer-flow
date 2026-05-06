from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEERFLOW_ROOT = BACKEND_ROOT.parent
SECOPS_SKILL_ROOT = DEERFLOW_ROOT / "skills" / "custom" / "secops"
SECOPS_AGENT_SOUL = BACKEND_ROOT / ".deer-flow" / "agents" / "secops-agent" / "SOUL.md"

SECOPS_SKILLS = {
    "ddos-attack-responder": SECOPS_SKILL_ROOT / "ddos-attack-responder" / "SKILL.md",
    "port-scanning-responder": SECOPS_SKILL_ROOT / "port-scanning-responder" / "SKILL.md",
    "mock-illegal-login-responder": SECOPS_SKILL_ROOT / "mock-illegal-login-responder" / "SKILL.md",
    "mock-external-ticket-responder": SECOPS_SKILL_ROOT / "mock-external-ticket-responder" / "SKILL.md",
}

FORBIDDEN_V1_DETAILS = (
    "deerflow.tools.builtins",
    "SecOpsAlertContextMiddleware",
    "hidden human message",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_secops_skills_keep_context_rules_inline_without_v2_contract_section():
    for skill_name, skill_path in SECOPS_SKILLS.items():
        text = _read(skill_path)

        assert "## V2 Context Contract" not in text, skill_name
        assert "active thread binding" in text, skill_name
        assert "`ok=false`" in text, skill_name
        assert "get_alert_workspace_context()" in text, skill_name


def test_secops_skills_do_not_reference_v1_runtime_internals():
    documents = {name: _read(path) for name, path in SECOPS_SKILLS.items()}
    documents["secops-agent/SOUL.md"] = _read(SECOPS_AGENT_SOUL)

    for document_name, text in documents.items():
        for forbidden in FORBIDDEN_V1_DETAILS:
            assert forbidden not in text, f"{document_name} references {forbidden}"


def test_false_positive_skills_use_v2_tool_confirmed_status_updates():
    for skill_name in ("ddos-attack-responder", "port-scanning-responder"):
        text = _read(SECOPS_SKILLS[skill_name])

        assert "Call `get_alert_workspace_context()` first" in text
        assert "If the tool returns `ok=false`, stop" in text
        assert 'update_alert_status(status="processed")' in text
        assert "Do not claim the alert was processed unless the status update returns `ok=true`" in text


def test_mock_illegal_login_skill_documents_complete_v2_sop():
    text = _read(SECOPS_SKILLS["mock-illegal-login-responder"])

    required_fragments = (
        "Call `get_alert_workspace_context()` first",
        '`alert.sourceIp`',
        '`commonIp`',
        'get_mock_auth_user_context(username="test")',
        'kick_mock_auth_user_sessions(username="test")',
        'disable_mock_auth_user(username="test")',
        'update_alert_status(status="processing")',
        'update_alert_status(status="processed")',
        'update_alert_status(status="failed")',
        "If any required remediation tool returns `ok=false`, mark the alert `failed`",
    )

    for fragment in required_fragments:
        assert fragment in text


def test_mock_external_ticket_skill_documents_callback_contract():
    text = _read(SECOPS_SKILLS["mock-external-ticket-responder"])

    required_fragments = (
        "Call `get_alert_workspace_context()` first",
        'update_alert_status(status="processing")',
        "create_mock_ticket()",
        "`ticketId`",
        "`externalTaskId`",
        "`jobId`",
        "Callback branch",
        "Do not create a new ticket",
        "get_mock_ticket_external_status(external_task_id=...)",
        'update_alert_status(status="processed")',
        'update_alert_status(status="failed")',
    )

    for fragment in required_fragments:
        assert fragment in text


def test_secops_agent_soul_explains_thread_bound_alert_recovery():
    text = _read(SECOPS_AGENT_SOUL)

    assert "runtime may only provide `thread_id`" in text
    assert "call `get_alert_workspace_context()` first" in text
    assert "recover `alert_id` from the active thread binding" in text
    assert "`alert_id` may be omitted" in text
