from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from aura.adapters.runtime.loader import RuntimeLoaderError
from aura.utils.archive import UnsafeArchiveError, extract_zip_safely


class SkillManifestValidationError(ValueError):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("Skill manifest validation failed.")
        self.errors = errors


@dataclass(slots=True)
class ValidatedSkillManifest:
    data: dict[str, Any]
    smoke_test_passed: bool


class SkillManifestValidator:
    def validate(self, manifest_yaml: str, *, zip_bytes: bytes | None = None) -> ValidatedSkillManifest:
        try:
            parsed = yaml.safe_load(manifest_yaml) or {}
        except yaml.YAMLError as exc:
            raise SkillManifestValidationError([{"field": "manifest", "message": str(exc)}]) from exc
        if not isinstance(parsed, dict):
            raise SkillManifestValidationError([{"field": "manifest", "message": "Manifest must decode to a mapping."}])

        errors = self._collect_errors(parsed)
        smoke_test_passed = False
        if not errors:
            try:
                smoke_test_passed = self._smoke_test_import(parsed, zip_bytes=zip_bytes)
            except RuntimeLoaderError as exc:
                errors.append({"field": "artifact", "message": str(exc)})
            if parsed.get("status") == "published" and not smoke_test_passed:
                errors.append({"field": "status", "message": "Manifest cannot declare published when smoke test fails."})
        if errors:
            raise SkillManifestValidationError(errors)
        return ValidatedSkillManifest(data=parsed, smoke_test_passed=smoke_test_passed)

    def _collect_errors(self, manifest: dict[str, Any]) -> list[dict[str, str]]:
        skill_type = manifest.get("skill_type", "sandbox_python")
        required = {"kind", "name", "version", "entrypoint", "status"}
        if skill_type == "mcp_client":
            required |= {"mcp_server_url", "mcp_auth", "exposed_tools", "timeout"}
        else:
            required |= {"runtime"}
        errors = [{"field": field, "message": "Field is required."} for field in sorted(required - set(manifest))]
        if errors:
            return errors

        if manifest.get("kind") != "skill":
            errors.append({"field": "kind", "message": "kind must be 'skill'."})
        if manifest.get("status") not in {"draft", "validated", "published", "deprecated"}:
            errors.append({"field": "status", "message": "Unsupported status."})
        if skill_type == "mcp_client":
            if not isinstance(manifest.get("exposed_tools"), list) or not manifest.get("exposed_tools"):
                errors.append({"field": "exposed_tools", "message": "exposed_tools must contain at least one tool."})
            if not isinstance(manifest.get("mcp_auth"), dict):
                errors.append({"field": "mcp_auth", "message": "mcp_auth must be an object."})
        elif manifest.get("runtime") != "sandbox-python":
            errors.append({"field": "runtime", "message": "runtime must be 'sandbox-python'."})
        return errors

    def _smoke_test_import(self, manifest: dict[str, Any], *, zip_bytes: bytes | None) -> bool:
        if manifest.get("skill_type") == "mcp_client":
            return True
        if not zip_bytes:
            return False
        entrypoint = str(manifest["entrypoint"])
        with tempfile.TemporaryDirectory(prefix="aura-skill-smoke-") as temp_dir:
            archive_path = Path(temp_dir) / "artifact.zip"
            archive_path.write_bytes(zip_bytes)
            with zipfile.ZipFile(archive_path) as archive:
                try:
                    extract_zip_safely(archive, temp_dir)
                except UnsafeArchiveError as exc:
                    raise RuntimeLoaderError(str(exc)) from exc
            module_path = (Path(temp_dir) / entrypoint).resolve()
            if not module_path.exists():
                raise RuntimeLoaderError(f"Skill entrypoint not found: {entrypoint}")
        return True
