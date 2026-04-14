from __future__ import annotations

import io
import zipfile

import pytest

from aura.adapters.registry.manifest_validator import ManifestValidationError, ManifestValidator
from aura.adapters.registry.skill_manifest_validator import SkillManifestValidationError, SkillManifestValidator


def _build_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_skill_manifest_validator_rejects_path_traversal() -> None:
    validator = SkillManifestValidator()
    manifest = "\n".join(
        [
            "kind: skill",
            "name: traversal-skill",
            "version: 1.0.0",
            "runtime: sandbox-python",
            "entrypoint: main.py",
            "status: validated",
        ]
    )

    with pytest.raises(SkillManifestValidationError) as excinfo:
        validator.validate(
            manifest,
            zip_bytes=_build_zip(
                {
                    "../escape.py": "print('bad')",
                    "main.py": "print('ok')",
                }
            ),
        )

    assert excinfo.value.errors == [
        {"field": "artifact", "message": "Archive member escapes destination: ../escape.py"}
    ]


def test_agent_manifest_validator_rejects_path_traversal() -> None:
    validator = ManifestValidator()
    manifest = "\n".join(
        [
            "kind: agent",
            "name: traversal-agent",
            "version: 1.0.0",
            "agent_type: single",
            "runtime: pydantic-ai",
            "entrypoint: agent.py:build",
            "allowed_tools: []",
            "allowed_spaces: []",
            "model_policy: default",
            "timeout_s: 30",
            "status: validated",
        ]
    )

    with pytest.raises(ManifestValidationError) as excinfo:
        validator.validate(
            manifest,
            zip_bytes=_build_zip(
                {
                    "../../escape.py": "print('bad')",
                    "agent.py": "def build(deps):\n    return deps\n",
                }
            ),
        )

    assert excinfo.value.errors == [
        {"field": "artifact", "message": "Archive member escapes destination: ../../escape.py"}
    ]
