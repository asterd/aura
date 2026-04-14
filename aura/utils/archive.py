from __future__ import annotations

import stat
import zipfile
from pathlib import Path


class UnsafeArchiveError(ValueError):
    pass


def extract_zip_safely(archive: zipfile.ZipFile, destination: str | Path) -> None:
    destination_path = Path(destination).resolve()
    for member in archive.infolist():
        member_path = member.filename
        if not member_path:
            continue
        target_path = (destination_path / member_path).resolve()
        if destination_path not in target_path.parents and target_path != destination_path:
            raise UnsafeArchiveError(f"Archive member escapes destination: {member_path}")
        if _is_symlink(member):
            raise UnsafeArchiveError(f"Archive member is a symlink: {member_path}")
    archive.extractall(destination_path)


def _is_symlink(member: zipfile.ZipInfo) -> bool:
    mode = member.external_attr >> 16
    return stat.S_ISLNK(mode)
