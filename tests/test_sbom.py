from __future__ import annotations

import importlib.util
from pathlib import Path

from wzlcarrot_cli import __version__

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gen_sbom.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_sbom", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sbom_structure():
    module = _load_module()
    sbom = module.build_sbom()
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"]
    assert sbom["metadata"]["component"]["name"] == "wzlcarrot-cli"
    assert sbom["metadata"]["component"]["version"] == __version__
    assert isinstance(sbom["components"], list) and sbom["components"]


def test_sbom_lists_dependencies_with_purls():
    module = _load_module()
    sbom = module.build_sbom()
    names = {c["name"].lower() for c in sbom["components"]}
    assert "httpx" in names and "typer" in names
    for component in sbom["components"]:
        assert component["purl"].startswith("pkg:pypi/")
        assert component["version"]
