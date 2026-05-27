from pathlib import Path

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.governance_scaffold import ensure_governance_scaffold
from openclaw_governance.regen_readme_agent_raci import run_regen_raci
from openclaw_governance.regen_readme_summary import run_regen_summary


def test_regen_write_then_check_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "gov"
    root.mkdir()
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=root)
    ensure_governance_scaffold(config)

    registry = {
        "version": 0.1,
        "agents": [{"id": "main", "name": "Main", "role": "Agent", "workspace": "/w"}],
        "raci_domains": {
            "platform": {
                "title": "Platform",
                "responsible": "main",
                "accountable": "Operator",
                "consulted": [],
                "informed": ["main"],
            }
        },
        "workflows": [],
    }
    reg_path = root / "workflows" / "registry.yaml"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(yaml.dump(registry), encoding="utf-8")

    (root / "governance.config.yaml").write_text(
        f"openclaw_home: {config.openclaw_home}\n"
        f"governance_root: {root}\n"
        "accountable_humans:\n  - Operator\n",
        encoding="utf-8",
    )

    assert run_regen_summary(config, write=True) == 0
    assert run_regen_raci(config, write=True) == 0
    assert run_regen_summary(config, check=True) == 0
    assert run_regen_raci(config, check=True) == 0
