# -*- coding: utf-8 -*-
"""Atomic output transaction for formal success, failure, and cache files."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _replace(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _to_bytes(content: str | bytes) -> bytes:
    return content if isinstance(content, bytes) else content.encode("utf-8")


def _write_temp(destination: Path, content: str | bytes) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_path = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temp_path = Path(raw_path)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(_to_bytes(content))
            file.flush()
            os.fsync(file.fileno())
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _restore(target: Path, previous: bytes | None) -> None:
    if previous is None:
        target.unlink(missing_ok=True)
        return
    temporary = _write_temp(target, previous)
    _replace(temporary, target)


def write_transaction(writes: dict[Path, str | bytes | None]) -> None:
    """Commit all files together or restore the exact prior bytes.

    ``None`` means that the file must not exist after a successful commit.
    The caller must fully validate cache and result payloads before invoking
    this function.
    """
    if not writes:
        return

    previous = {path: path.read_bytes() if path.exists() else None for path in writes}
    temporaries: dict[Path, Path] = {}
    try:
        for path, content in writes.items():
            if content is not None:
                temporaries[path] = _write_temp(path, content)

        for path in writes:
            temporary = temporaries.get(path)
            if temporary is None:
                path.unlink(missing_ok=True)
            else:
                _replace(temporary, path)
    except Exception:
        rollback_errors: list[Exception] = []
        for path, old_content in previous.items():
            try:
                _restore(path, old_content)
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise RuntimeError(
                f"输出事务失败且回滚不完整：{rollback_errors[0]}"
            )
        raise
    finally:
        for temporary in temporaries.values():
            temporary.unlink(missing_ok=True)
