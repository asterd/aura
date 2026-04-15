from __future__ import annotations

import inspect
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from aura.domain.contracts import CronTrigger, EventTrigger
from aura.utils.archive import UnsafeArchiveError, extract_zip_safely


class ManifestValidationError(ValueError):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("Manifest validation failed.")
        self.errors = errors


@dataclass(slots=True)
class ValidatedManifest:
    data: dict[str, Any]
    smoke_test_passed: bool


class ManifestValidator:
    _required_fields = {
        "kind",
        "name",
        "version",
        "agent_type",
        "runtime",
        "entrypoint",
        "allowed_tools",
        "allowed_spaces",
        "model_policy",
        "timeout_s",
        "status",
    }

    def validate(self, manifest_yaml: str, *, zip_bytes: bytes) -> ValidatedManifest:
        try:
            parsed = yaml.safe_load(manifest_yaml) or {}
        except yaml.YAMLError as exc:
            raise ManifestValidationError([{"field": "manifest", "message": str(exc)}]) from exc

        if not isinstance(parsed, dict):
            raise ManifestValidationError([{"field": "manifest", "message": "Manifest must decode to a mapping."}])

        errors = self._collect_errors(parsed)
        smoke_test_passed = False
        if not errors:
            try:
                smoke_test_passed = self._smoke_test_import(zip_bytes=zip_bytes, entrypoint=str(parsed["entrypoint"]))
            except ValueError as exc:
                errors.append({"field": "artifact", "message": str(exc)})
            if parsed.get("status") == "published" and not smoke_test_passed:
                errors.append({"field": "status", "message": "Manifest cannot declare published when smoke test fails."})

        if errors:
            raise ManifestValidationError(errors)
        return ValidatedManifest(data=parsed, smoke_test_passed=smoke_test_passed)

    def _collect_errors(self, manifest: dict[str, Any]) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        missing = sorted(field for field in self._required_fields if field not in manifest)
        errors.extend({"field": field, "message": "Field is required."} for field in missing)
        if missing:
            return errors

        if manifest.get("kind") != "agent":
            errors.append({"field": "kind", "message": "kind must be 'agent'."})
        if manifest.get("runtime") != "pydantic-ai":
            errors.append({"field": "runtime", "message": "runtime must be 'pydantic-ai'."})
        if manifest.get("agent_type") not in {"single", "orchestrator", "triggered", "autonomous"}:
            errors.append({"field": "agent_type", "message": "Unsupported agent_type."})
        if manifest.get("status") not in {"draft", "validated", "published", "deprecated"}:
            errors.append({"field": "status", "message": "Unsupported status."})
        if not isinstance(manifest.get("allowed_tools"), list):
            errors.append({"field": "allowed_tools", "message": "allowed_tools must be a list."})
        if not isinstance(manifest.get("allowed_spaces"), list):
            errors.append({"field": "allowed_spaces", "message": "allowed_spaces must be a list."})
        if not isinstance(manifest.get("timeout_s"), int):
            errors.append({"field": "timeout_s", "message": "timeout_s must be an integer."})

        triggers = manifest.get("triggers")
        agent_type = manifest.get("agent_type")
        if agent_type in {"triggered", "autonomous"}:
            if not isinstance(triggers, list) or not triggers:
                errors.append({"field": "triggers", "message": "Triggers are required for triggered/autonomous agents."})
            else:
                for idx, trigger in enumerate(triggers):
                    if not isinstance(trigger, dict):
                        errors.append({"field": f"triggers[{idx}]", "message": "Trigger must be an object."})
                        continue
                    try:
                        if trigger.get("type") == "cron":
                            CronTrigger.model_validate(trigger)
                            self._validate_cron_expression(str(trigger.get("cron_expression", "")))
                        elif trigger.get("type") == "event":
                            EventTrigger.model_validate(trigger)
                        else:
                            errors.append({"field": f"triggers[{idx}].type", "message": "Unsupported trigger type."})
                    except Exception as exc:
                        errors.append({"field": f"triggers[{idx}]", "message": str(exc)})
        elif triggers:
            errors.append({"field": "triggers", "message": "Triggers are only valid for triggered/autonomous agents."})
        return errors

    def _validate_cron_expression(self, expression: str) -> None:
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError("Cron expression must use five fields.")
        for part in parts:
            if part == "*":
                continue
            if part.startswith("*/") and part[2:].isdigit():
                continue
            if part.isdigit():
                continue
            raise ValueError(f"Unsupported cron token '{part}'.")

    def _smoke_test_import(self, *, zip_bytes: bytes, entrypoint: str) -> bool:
        from aura.adapters.runtime.loader import RuntimeLoader

        with tempfile.TemporaryDirectory(prefix="aura-agent-smoke-") as temp_dir:
            archive_path = Path(temp_dir) / "artifact.zip"
            archive_path.write_bytes(zip_bytes)
            with zipfile.ZipFile(archive_path) as archive:
                try:
                    extract_zip_safely(archive, temp_dir)
                except UnsafeArchiveError as exc:
                    raise ValueError(str(exc)) from exc
            build_fn = RuntimeLoader().load_build_fn_from_directory(Path(temp_dir), entrypoint)
            signature = inspect.signature(build_fn)
            return len(signature.parameters) == 1
