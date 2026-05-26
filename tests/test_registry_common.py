from openclaw_governance.registry_common import resolve_workflow_raci_domain


def test_resolve_workflow_raci_domain_prefix() -> None:
    registry = {
        "raci_workflow_domains": {"explicit": {}},
        "raci_domains": {
            "governance_registry": {},
            "personal_ops": {},
        },
    }
    assert (
        resolve_workflow_raci_domain("main.workflow_registry_drift_check", registry)
        == "governance_registry"
    )
    assert resolve_workflow_raci_domain("finance.ai_basket.daily_pipeline", registry) is None
