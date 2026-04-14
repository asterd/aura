from __future__ import annotations

import hashlib
import importlib.util
import inspect
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from aura.adapters.s3.client import S3Client
from aura.utils.archive import UnsafeArchiveError, extract_zip_safely


class RuntimeLoaderError(RuntimeError):
    pass


class RuntimeLoader:
    def __init__(self, s3_client: S3Client | None = None) -> None:
        self._s3 = s3_client or S3Client()

    async def load_build_fn(self, artifact_ref: str, entrypoint: str, artifact_sha256: str) -> Callable:
        temp_dir = Path(tempfile.mkdtemp(prefix="aura-agent-runtime-"))
        try:
            bucket, key = self._parse_s3_ref(artifact_ref)
            raw_zip = await self._s3.download_file(bucket, key)
            actual_sha = hashlib.sha256(raw_zip).hexdigest()
            if actual_sha != artifact_sha256:
                raise RuntimeLoaderError(f"Artifact sha256 mismatch: expected {artifact_sha256}, got {actual_sha}.")

            archive_path = temp_dir / "artifact.zip"
            archive_path.write_bytes(raw_zip)
            with zipfile.ZipFile(archive_path) as archive:
                try:
                    extract_zip_safely(archive, temp_dir)
                except UnsafeArchiveError as exc:
                    raise RuntimeLoaderError(str(exc)) from exc
            build_fn = self.load_build_fn_from_directory(temp_dir, entrypoint)
            setattr(build_fn, "__aura_temp_dir__", str(temp_dir))
            return build_fn
        except Exception:
            await self.cleanup_temp_dir(temp_dir)
            raise

    def load_build_fn_from_directory(self, base_dir: Path, entrypoint: str) -> Callable:
        module_path_str, _, function_name = entrypoint.partition(":")
        if not module_path_str or not function_name:
            raise RuntimeLoaderError("Entrypoint must use the format path.py:function_name.")

        module_path = (base_dir / module_path_str).resolve()
        if base_dir.resolve() not in module_path.parents and module_path != base_dir.resolve():
            raise RuntimeLoaderError("Entrypoint must stay inside the extracted artifact directory.")
        if not module_path.exists():
            raise RuntimeLoaderError(f"Entrypoint module not found: {module_path_str}")

        spec = importlib.util.spec_from_file_location(f"aura_runtime_{module_path.stem}", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeLoaderError(f"Unable to load module from {module_path_str}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        build_fn = getattr(module, function_name, None)
        if build_fn is None or not callable(build_fn):
            raise RuntimeLoaderError(f"Entrypoint function '{function_name}' not found.")

        signature = inspect.signature(build_fn)
        if len(signature.parameters) != 1:
            raise RuntimeLoaderError("build must accept exactly one parameter: AgentDeps.")
        return build_fn

    async def cleanup_temp_dir(self, temp_dir: str | Path | None) -> None:
        if temp_dir is None:
            return
        shutil.rmtree(Path(temp_dir), ignore_errors=True)

    def _parse_s3_ref(self, artifact_ref: str) -> tuple[str, str]:
        if not artifact_ref.startswith("s3://"):
            raise RuntimeLoaderError("Artifact ref must start with s3://")
        bucket_and_key = artifact_ref.removeprefix("s3://")
        bucket, _, key = bucket_and_key.partition("/")
        if not bucket or not key:
            raise RuntimeLoaderError("Artifact ref must include bucket and key.")
        return bucket, key
