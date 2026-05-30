from pathlib import Path

from openclaw_governance.agent_scope import (
    agent_explicitly_promoted_to_broadcast,
    apply_plugin_scope_to_agent_entry,
    is_plugin_scoped_agent,
)
from openclaw_governance.check_registry import Check, check_agents_and_raci_domains
from openclaw_governance.config import GovernanceConfig
from openclaw_governance.materialize import agents_registry_entries
from openclaw_governance.discover import DiscoveredAgent, DiscoveryResult
from openclaw_governance.registry_common import agents_requiring_raci_broadcast
from openclaw_governance.registry_merge import merge_agents


def test_is_plugin_scoped_agent_by_id() -> None:
    assert is_plugin_scoped_agent("mnemospark", "/tmp/workspace", {"mnemospark"}, [])


def test_is_plugin_scoped_agent_by_workspace_root(tmp_path: Path) -> None:
    root = tmp_path / "extensions" / "mnemospark"
    root.mkdir(parents=True)
    workspace = str(root / "agent")
    assert is_plugin_scoped_agent("helper", workspace, set(), [root])


def _agent(agent_id: str, **extra: object) -> dict:
    return {
        "id": agent_id,
        "name": agent_id.title(),
        "role": "agent",
        "workspace": f"/tmp/{agent_id}",
        **extra,
    }

def test_core_agent_not_plugin_scoped() -> None:
    assert not is_plugin_scoped_agent("main", "/home/user/.openclaw/workspace", {"mnemospark"}, [])


def test_agents_registry_entries_marks_plugin_agent() -> None:
    result = DiscoveryResult(
        generated_at="2026-05-30T00:00:00Z",
        openclaw_home="/home/user/.openclaw",
        openclaw_config_path="/home/user/.openclaw/openclaw.json",
        agents=[
            DiscoveredAgent(
                agent_id="mnemospark",
                name="Mnemospark",
                role="plugin agent",
                workspace="/home/user/.openclaw/extensions/mnemospark",
            )
        ],
    )
    config = GovernanceConfig(
        openclaw_home=Path("/home/user/.openclaw"),
        governance_root=Path("/tmp/gov"),
    )
    entries = agents_registry_entries(
        result,
        config,
        plugin_ids={"mnemospark"},
        plugin_roots=[],
    )
    assert entries[0]["governance_scope"] == "plugin"
    assert entries[0]["raci_broadcast_excluded"] is True


def test_merge_agents_refreshes_plugin_scope_on_repromote() -> None:
    existing = [{"id": "mnemospark", "name": "Mnemospark", "role": "plugin", "workspace": "/w"}]
    proposed = [
        {
            "id": "mnemospark",
            "name": "Mnemospark",
            "role": "plugin",
            "workspace": "/w",
            "governance_scope": "plugin",
            "raci_broadcast_excluded": True,
        }
    ]
    merged = merge_agents(existing, proposed)
    assert merged[0]["governance_scope"] == "plugin"
    assert merged[0]["raci_broadcast_excluded"] is True


def test_merge_agents_preserves_explicit_broadcast_promotion() -> None:
    existing = [
        {
            "id": "mnemospark",
            "name": "Mnemospark",
            "role": "plugin",
            "workspace": "/w",
            "governance_scope": "core",
            "raci_broadcast_excluded": False,
        }
    ]
    proposed = [
        {
            "id": "mnemospark",
            "name": "Mnemospark",
            "role": "plugin",
            "workspace": "/w",
            "governance_scope": "plugin",
            "raci_broadcast_excluded": True,
        }
    ]
    merged = merge_agents(existing, proposed)
    assert merged[0]["governance_scope"] == "core"
    assert merged[0]["raci_broadcast_excluded"] is False


def test_check_platform_domains_allows_plugin_agent_outside_informed(tmp_path: Path) -> None:
    registry = {
        "agents": [
            _agent("main"),
            _agent(
                "mnemospark",
                governance_scope="plugin",
                raci_broadcast_excluded=True,
            ),
        ],
        "raci_domains": {
            "platform_notion": {
                "title": "Notion",
                "responsible": "main",
                "accountable": "Operator",
                "consulted": [],
                "informed": ["main"],
            },
            "platform_google": {
                "title": "Google",
                "responsible": "main",
                "accountable": "Operator",
                "consulted": [],
                "informed": ["main"],
            },
        },
    }
    check = Check()
    config = GovernanceConfig(
        openclaw_home=tmp_path,
        governance_root=tmp_path,
        accountable_humans=["Operator"],
    )
    check_agents_and_raci_domains(registry, check, config)
    assert not check.errors


def test_check_platform_domains_still_requires_core_broadcast_agents(tmp_path: Path) -> None:
    registry = {
        "agents": [_agent("main"), _agent("research")],
        "raci_domains": {
            "platform_notion": {
                "title": "Notion",
                "responsible": "main",
                "accountable": "Operator",
                "consulted": [],
                "informed": ["main"],
            },
        },
    }
    check = Check()
    config = GovernanceConfig(
        openclaw_home=tmp_path,
        governance_root=tmp_path,
        accountable_humans=["Operator"],
    )
    check_agents_and_raci_domains(registry, check, config)
    assert any("missing: research" in error for error in check.errors)


def test_agents_requiring_raci_broadcast_honors_governance_scope() -> None:
    registry = {
        "agents": [
            {"id": "main"},
            {"id": "mnemospark", "governance_scope": "plugin"},
        ]
    }
    assert agents_requiring_raci_broadcast(registry) == {"main"}


def test_agent_explicitly_promoted_to_broadcast() -> None:
    assert agent_explicitly_promoted_to_broadcast({"governance_scope": "core"})
    assert agent_explicitly_promoted_to_broadcast({"raci_broadcast_excluded": False})
    assert not agent_explicitly_promoted_to_broadcast({"governance_scope": "plugin"})


def test_apply_plugin_scope_to_agent_entry() -> None:
    entry: dict = {"id": "mnemospark"}
    apply_plugin_scope_to_agent_entry(entry, plugin_scoped=True)
    assert entry["governance_scope"] == "plugin"
    assert entry["raci_broadcast_excluded"] is True
