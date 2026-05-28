from pathlib import Path

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import CronJob, DiscoveredAgent, DiscoveryResult, workflow_id_for_cron
from openclaw_governance.materialize import materialize_from_discovery
from openclaw_governance.registry_common import (
    DEFAULT_DOMAIN_PREFIX_RULES,
    agent_raci_domain_key,
    effective_domain_prefix_rules,
    ensure_raci_domains,
    resolve_workflow_raci_domain,
)


def test_agent_raci_domain_key_from_full_agent_id() -> None:
    assert agent_raci_domain_key("billing-bot") == "billing_bot_ops"
    assert agent_raci_domain_key("research") == "research_ops"


def test_resolve_any_agent_cron_via_effective_prefix_rules() -> None:
    registry = {
        "agents": [{"id": "main"}, {"id": "billing-bot"}],
        "raci_workflow_domains": {"explicit": {}},
        "raci_domains": {
            "governance_registry": {},
            "personal_ops": {},
            "billing_bot_ops": {},
        },
    }
    prefix_rules = effective_domain_prefix_rules(DEFAULT_DOMAIN_PREFIX_RULES, registry)
    assert (
        resolve_workflow_raci_domain("billing-bot.cron.nightly_invoice", registry, prefix_rules)
        == "billing_bot_ops"
    )


def test_materialize_creates_per_agent_ops_domain_for_any_agent(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    agent_id = "billing-bot"
    cron_name = "Nightly Invoice"
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(config.openclaw_home),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[
            DiscoveredAgent(
                agent_id=agent_id,
                name="Billing",
                role="Automation",
                workspace=str(tmp_path / "ws"),
                cron_jobs=[
                    CronJob(
                        agent_id=agent_id,
                        job_id="job-1",
                        name=cron_name,
                        enabled=True,
                        schedule="0 2 * * *",
                        message_preview="run billing",
                    )
                ],
            )
        ],
        runbooks=[],
    )

    materialize_from_discovery(result, config, write=True)

    workflow_id = workflow_id_for_cron(agent_id, cron_name)
    registry = yaml.safe_load((gov / "workflows" / "registry.yaml").read_text(encoding="utf-8"))
    assert "billing_bot_ops" in registry["raci_domains"]
    workflow = next(item for item in registry["workflows"] if item["id"] == workflow_id)
    assert workflow["raci_domain"] == "billing_bot_ops"


def test_ensure_raci_domains_init_only_skips_when_populated() -> None:
    registry = {
        "raci_domains": {
            "main_ops": {
                "title": "Curated",
                "responsible": "main",
                "accountable": "Woodrow",
                "consulted": [],
                "informed": [],
            }
        }
    }
    ensure_raci_domains(registry, ["main", "research"], accountable="Operator", init_only=True)
    assert "research_ops" not in registry["raci_domains"]
    assert registry["raci_domains"]["main_ops"]["title"] == "Curated"


def test_ensure_raci_domains_merges_without_overwriting() -> None:
    registry = {
        "raci_domains": {
            "personal_ops": {
                "title": "Custom",
                "responsible": "main",
                "accountable": "Woodrow",
                "consulted": [],
                "informed": [],
            }
        }
    }
    ensure_raci_domains(registry, ["main", "research"], accountable="Operator")
    assert registry["raci_domains"]["personal_ops"]["accountable"] == "Woodrow"
    assert "research_ops" in registry["raci_domains"]
    assert registry["raci_domains"]["research_ops"]["responsible"] == "research"
