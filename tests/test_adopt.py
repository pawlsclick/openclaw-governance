from pathlib import Path

import yaml

from openclaw_governance.adopt import run_adopt
from openclaw_governance.config import GovernanceConfig


def _write_registry(root: Path, workflows: list[dict]) -> None:
    reg_dir = root / "workflows"
    reg_dir.mkdir(parents=True, exist_ok=True)
    (reg_dir / "registry.yaml").write_text(
        yaml.dump({"workflows": workflows, "agents": [], "raci_domains": {}}),
        encoding="utf-8",
    )


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
