from pathlib import Path

import yaml

from openclaw_governance.adopt import run_adopt
from openclaw_governance.config import GovernanceConfig


def _write_registry(root: Path, workflows: list[dict], **extra: object) -> None:
    reg_dir = root / "workflows"
    reg_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "version": 0.2,
        "source_note": "custom metadata",
        "workflows": workflows,
        "agents": [],
        "raci_domains": {},
    }
    data.update(extra)
    (reg_dir / "registry.yaml").write_text(yaml.dump(data), encoding="utf-8")


def test_adopt_dry_run(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "governance.config.yaml").write_text("openclaw_home: /\n", encoding="utf-8")
    _write_registry(source, [{"id": "main.cron.test", "status": "discovered", "title": "Test"}])

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=target)
    code, report = run_adopt(config, source_root=source, write=False)
    assert code == 0
    assert report["dry_run"] is True
    assert not (target / "workflows" / "registry.yaml").exists()


def test_adopt_merges_registry(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "governance.config.yaml").write_text("openclaw_home: /\n", encoding="utf-8")
    (target / "governance.config.yaml").write_text(
        f"openclaw_home: {tmp_path / 'oc'}\ngovernance_root: {target}\n",
        encoding="utf-8",
    )
    _write_registry(source, [{"id": "main.cron.new", "status": "discovered", "title": "New"}])
    _write_registry(
        target,
        [{"id": "main.cron.existing", "status": "active", "title": "Keep", "purpose": "Important"}],
    )

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=target)
    code, report = run_adopt(config, source_root=source, write=True)
    assert code == 0
    registry = yaml.safe_load((target / "workflows" / "registry.yaml").read_text(encoding="utf-8"))
    ids = {row["id"] for row in registry["workflows"]}
    assert "main.cron.new" in ids
    assert "main.cron.existing" in ids
    active = next(row for row in registry["workflows"] if row["id"] == "main.cron.existing")
    assert active["purpose"] == "Important"
    assert report.get("report_path")


def test_adopt_source_authoritative_config_and_docs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    (source / "governance.config.yaml").write_text(
        "openclaw_home: /old/home\n"
        "governance_root: /old/gov\n"
        "accountable_humans:\n  - Custom Human\n"
        "domain_prefix_rules:\n  - prefix: custom.\n    domain: custom_domain\n",
        encoding="utf-8",
    )
    (target / "governance.config.yaml").write_text(
        f"openclaw_home: {tmp_path / 'oc'}\n"
        f"governance_root: {target}\n"
        "accountable_humans:\n  - Generic Operator\n",
        encoding="utf-8",
    )

    _write_registry(
        source,
        [{"id": "main.cron.x", "status": "discovered", "title": "X"}],
        custom_registry_field="preserve-me",
    )
    _write_registry(target, [])

    (source / "workflows" / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (source / "workflows" / "README.md").write_text("# Workflows\n", encoding="utf-8")
    runbooks = source / "workflows" / "runbooks"
    runbooks.mkdir(parents=True)
    (runbooks / "main.custom.runbook.md").write_text("# Custom\n", encoding="utf-8")

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=target)
    code, report = run_adopt(config, source_root=source, write=True)
    assert code == 0

    adopted_config = yaml.safe_load((target / "governance.config.yaml").read_text(encoding="utf-8"))
    assert adopted_config["accountable_humans"] == ["Custom Human"]
    assert adopted_config["governance_root"] == str(target)
    assert adopted_config["openclaw_home"] == str(tmp_path / "oc")

    registry = yaml.safe_load((target / "workflows" / "registry.yaml").read_text(encoding="utf-8"))
    assert registry.get("custom_registry_field") == "preserve-me"
    assert registry.get("source_note") == "custom metadata"

    assert (target / "workflows" / "CHANGELOG.md").is_file()
    assert (target / "workflows" / "README.md").is_file()
    assert (target / "workflows" / "runbooks" / "main.custom.runbook.md").is_file()

    config_diff = report.get("config") or {}
    assert "accountable_humans" in config_diff.get("overwritten", []) or "accountable_humans" in config_diff.get(
        "added_from_source", []
    )


def test_adopt_keep_target_config(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "governance.config.yaml").write_text(
        "accountable_humans:\n  - From Source\n", encoding="utf-8"
    )
    (target / "governance.config.yaml").write_text(
        f"openclaw_home: {tmp_path / 'oc'}\n"
        f"governance_root: {target}\n"
        "accountable_humans:\n  - Keep Target\n",
        encoding="utf-8",
    )
    _write_registry(source, [])
    _write_registry(target, [])

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=target)
    run_adopt(config, source_root=source, write=True, keep_target_config=True)
    adopted = yaml.safe_load((target / "governance.config.yaml").read_text(encoding="utf-8"))
    assert adopted["accountable_humans"] == ["Keep Target"]
