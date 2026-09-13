#!/usr/bin/env python3
"""Generate a CycloneDX SBOM from the installed environment.

    python scripts/gen_sbom.py > dist/sbom.cdx.json

Dependency-free: reads distribution metadata via importlib.metadata.
"""

from __future__ import annotations

import json
import sys
from importlib import metadata

from wzlcarrot_cli import __version__


def _license_name(dist: metadata.Distribution) -> str | None:
    meta = dist.metadata
    expression = meta.get("License-Expression") or meta.get("License")
    if expression and expression.strip():
        return expression.strip()
    for classifier in meta.get_all("Classifier") or []:
        prefix = "License ::"
        if classifier.startswith(prefix):
            return classifier.split("::")[-1].strip()
    return None


def build_sbom() -> dict:
    components = []
    for dist in metadata.distributions():
        name = (dist.metadata.get("Name") or "").strip()
        if not name:
            continue
        component = {
            "type": "library",
            "name": name,
            "version": dist.version,
            "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{dist.version}",
        }
        license_name = _license_name(dist)
        if license_name:
            component["licenses"] = [{"license": {"name": license_name}}]
        components.append(component)

    components.sort(key=lambda item: item["name"].lower())
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "wzlcarrot-cli",
                "version": __version__,
                "purl": f"pkg:pypi/wzlcarrot-cli@{__version__}",
            }
        },
        "components": components,
    }


def main() -> None:
    json.dump(build_sbom(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
