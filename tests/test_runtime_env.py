from pathlib import Path

from zapret_hub.runtime_env import development_install_root


def test_development_install_root_finds_project_from_nested_module(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    nested_module = project_root / "src" / "zapret_hub" / "ui" / "web_window.py"
    nested_module.parent.mkdir(parents=True)
    nested_module.touch()
    (project_root / "pyproject.toml").touch()

    assert development_install_root(nested_module) == project_root
