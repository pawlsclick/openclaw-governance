from pathlib import Path

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.inject_agents import (
    BEGIN,
    END,
    has_stanza,
    inject_file,
    prune_file,
    remove_stanza_from_text,
    render_stanza,
    resolve_inject_agent_ids,
)


def _config(tmp_path: Path, **kwargs: object) -> GovernanceConfig:
    return GovernanceConfig(
        openclaw_home=tmp_path / "oc",
        governance_root=tmp_path / "gov",
        remote_url=kwargs.get("remote_url"),  # type: ignore[arg-type]
        inject_included=kwargs.get("inject_included"),  # type: ignore[arg-type]
    )


def test_render_stanza_includes_remote() -> None:
    config = GovernanceConfig(
        openclaw_home=Path("/oc"),
        governance_root=Path("/gov"),
        remote_url="https://github.com/you/gov.git",
    )
    stanza = render_stanza(config)
    assert "Governance remote" in stanza
    assert "https://github.com/you/gov.git" in stanza


def test_resolve_inject_agent_ids_cli_overrides() -> None:
    config = GovernanceConfig(
        openclaw_home=Path("/oc"),
        governance_root=Path("/gov"),
        inject_included=["main"],
    )
    assert resolve_inject_agent_ids(config, cli_agents=["other"]) == {"other"}


def test_resolve_inject_empty_list() -> None:
    config = GovernanceConfig(
        openclaw_home=Path("/oc"),
        governance_root=Path("/gov"),
        inject_included=[],
    )
    assert resolve_inject_agent_ids(config) == set()


def test_remove_stanza_from_text() -> None:
    text = f"intro\n\n{BEGIN}\nbody\n{END}\n\nfooter\n"
    updated, removed = remove_stanza_from_text(text)
    assert removed
    assert BEGIN not in updated
    assert "intro" in updated
    assert "footer" in updated


def test_inject_and_prune_file(tmp_path: Path) -> None:
    agents_md = tmp_path / "AGENTS.md"
    config = _config(tmp_path, remote_url="https://github.com/you/gov.git")
    stanza = render_stanza(config)

    inject_file(agents_md, stanza, write=True)
    assert has_stanza(agents_md.read_text(encoding="utf-8"))

    action = prune_file(agents_md, write=True)
    assert action == "pruned"
    assert not has_stanza(agents_md.read_text(encoding="utf-8"))


def test_inject_file_dry_run_prefix(tmp_path: Path) -> None:
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Agent\n", encoding="utf-8")
    config = _config(tmp_path)
    stanza = render_stanza(config)
    action = inject_file(agents_md, stanza, write=False)
    assert action == "would_appended"
