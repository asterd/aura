from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from apps.api.config import settings
from aura.adapters.s3.client import S3Client
from aura.domain.contracts import NetworkEgressMode, SandboxArtifact, SandboxInput, SandboxResult
from aura.utils.archive import UnsafeArchiveError, extract_zip_safely


class DockerSandboxProvider:
    def __init__(self, *, s3_client: S3Client | None = None, docker_binary: str | None = None) -> None:
        self._s3 = s3_client or S3Client()
        self._docker_binary = docker_binary or settings.sandbox_docker_binary

    async def run(self, sandbox_input: SandboxInput) -> SandboxResult:
        if not await self.health_check():
            return SandboxResult(
                status="failed",
                error_message="Docker not available",
                wall_time_s=0.0,
                exit_code=None,
            )

        started_at = time.monotonic()
        temp_dir = Path(tempfile.mkdtemp(prefix="aura-skill-run-"))
        workspace_dir = temp_dir / "workspace"
        artifacts_dir = temp_dir / "artifacts"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        container_name = f"aura-skill-{sandbox_input.skill_version_id.hex[:12]}-{uuid.uuid4().hex[:8]}"
        try:
            await self._prepare_workspace(workspace_dir, sandbox_input)
            command = self._build_command(
                sandbox_input=sandbox_input,
                workspace_dir=workspace_dir,
                artifacts_dir=artifacts_dir,
                container_name=container_name,
            )
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=sandbox_input.profile.max_wall_time_s)
            except asyncio.TimeoutError:
                await self._terminate_container(container_name)
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.communicate()
                return SandboxResult(
                    status="timeout",
                    error_message="Sandbox timeout exceeded.",
                    wall_time_s=time.monotonic() - started_at,
                    exit_code=None,
                    artifacts=await self._upload_artifacts(
                        sandbox_input=sandbox_input,
                        artifacts_dir=artifacts_dir,
                    ),
                )

            artifacts = await self._upload_artifacts(sandbox_input=sandbox_input, artifacts_dir=artifacts_dir)
            return SandboxResult(
                status="succeeded" if process.returncode == 0 else "failed",
                output=self._parse_output(stdout) if process.returncode == 0 else None,
                error_message=self._render_error(stderr, stdout) if process.returncode != 0 else None,
                artifacts=artifacts,
                wall_time_s=time.monotonic() - started_at,
                exit_code=process.returncode,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def health_check(self) -> bool:
        try:
            process = await asyncio.create_subprocess_exec(
                self._docker_binary,
                "version",
                "--format",
                "{{.Server.Version}}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return False
        return await process.wait() == 0

    async def _prepare_workspace(self, workspace_dir: Path, sandbox_input: SandboxInput) -> None:
        if sandbox_input.artifact_ref and sandbox_input.artifact_ref.startswith("s3://"):
            bucket, key = self._parse_s3_ref(sandbox_input.artifact_ref)
            archive_bytes = await self._s3.download_file(bucket, key)
            archive_path = workspace_dir / "artifact.zip"
            archive_path.write_bytes(archive_bytes)
            with zipfile.ZipFile(archive_path) as archive:
                try:
                    extract_zip_safely(archive, workspace_dir)
                except UnsafeArchiveError as exc:
                    raise RuntimeError(str(exc)) from exc
            archive_path.unlink(missing_ok=True)
        (workspace_dir / "input.json").write_text(json.dumps(sandbox_input.input_obj), encoding="utf-8")

    def _build_command(
        self,
        *,
        sandbox_input: SandboxInput,
        workspace_dir: Path,
        artifacts_dir: Path,
        container_name: str,
    ) -> list[str]:
        profile = sandbox_input.profile
        manifest = profile
        del manifest
        command = [
            self._docker_binary,
            "run",
            "--rm",
            "--name",
            container_name,
            "-v",
            f"{workspace_dir}:/workspace",
            "-v",
            f"{artifacts_dir}:/artifacts",
            "-w",
            "/workspace",
            "--memory",
            f"{profile.max_memory_mb}m",
        ]
        raw_cpus = profile.max_cpu_seconds / max(profile.max_wall_time_s, 1)
        available_cpus = float(os.cpu_count() or 1)
        cpus = min(max(raw_cpus, 0.1), max(available_cpus, 0.1))
        command.extend(["--cpus", f"{cpus:.2f}"])
        if profile.network_egress == NetworkEgressMode.none:
            command.extend(["--network", "none"])
        for env_name in profile.env_vars_allowed:
            env_value = os.environ.get(env_name)
            if env_value is not None:
                command.extend(["-e", f"{env_name}={env_value}"])
        command.append(settings.sandbox_default_python_image)
        command.extend(["python", sandbox_input.entrypoint])
        return command

    def _parse_output(self, stdout: bytes) -> dict:
        payload = stdout.decode("utf-8").strip()
        if not payload:
            return {}
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Sandbox stdout did not contain valid JSON: {payload}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Sandbox stdout JSON must be an object.")
        return parsed

    def _render_error(self, stderr: bytes, stdout: bytes) -> str:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        return stderr_text or stdout_text or "Sandbox execution failed."

    async def _upload_artifacts(self, *, sandbox_input: SandboxInput, artifacts_dir: Path) -> list[SandboxArtifact]:
        uploaded: list[SandboxArtifact] = []
        for artifact_path in sorted(path for path in artifacts_dir.rglob("*") if path.is_file()):
            relative_name = artifact_path.relative_to(artifacts_dir).as_posix()
            key = f"skills/{sandbox_input.skill_version_id}/{uuid.uuid4().hex}-{relative_name}"
            content = artifact_path.read_bytes()
            content_type = mimetypes.guess_type(artifact_path.name)[0] or "application/octet-stream"
            ref = await self._s3.upload_file(settings.s3_bucket_name, key, content, content_type)
            uploaded.append(
                SandboxArtifact(
                    name=relative_name,
                    content_type=content_type,
                    size_bytes=artifact_path.stat().st_size,
                    s3_ref=ref,
                )
            )
        return uploaded

    async def _terminate_container(self, container_name: str) -> None:
        process = await asyncio.create_subprocess_exec(
            self._docker_binary,
            "rm",
            "-f",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.communicate()

    def _parse_s3_ref(self, artifact_ref: str) -> tuple[str, str]:
        bucket_and_key = artifact_ref.removeprefix("s3://")
        bucket, _, key = bucket_and_key.partition("/")
        if not bucket or not key:
            raise ValueError("Artifact ref must include bucket and key.")
        return bucket, key
