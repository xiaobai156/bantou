# -*- coding: utf-8 -*-
"""Atomic output transaction for formal success, failure, and cache files."""

from __future__ import annotations

import hashlib
import msvcrt
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

_PROCESS_LOCK = threading.RLock()
_PROJECT_KEY = hashlib.sha256(
    str(Path(__file__).resolve().parents[2]).encode("utf-8")
).hexdigest()[:16]
_LOCK_PATH = Path(tempfile.gettempdir()) / f"bantou-{_PROJECT_KEY}-output.lock"
_LOCK_STATE = threading.local()


@contextmanager
def formal_write_lock():
    """Serialize cache read-modify-write and formal outputs for this project."""
    with _PROCESS_LOCK:
        depth = int(getattr(_LOCK_STATE, "depth", 0))
        if depth:
            _LOCK_STATE.depth = depth + 1
            try:
                yield
            finally:
                _LOCK_STATE.depth = depth
            return

        with _LOCK_PATH.open("a+b") as handle:
            _lock_handle(handle)
            _LOCK_STATE.depth = 1
            try:
                yield
            finally:
                _LOCK_STATE.depth = 0
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _lock_handle(handle) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    deadline = time.monotonic() + 30
    while True:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError("等待正式输出锁超过30秒")
            time.sleep(0.05)


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


def _write_transaction_unlocked(writes: dict[Path, str | bytes | None]) -> None:
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
            ) from rollback_errors[0]
        raise
    finally:
        for temporary in temporaries.values():
            temporary.unlink(missing_ok=True)


def write_transaction(writes: dict[Path, str | bytes | None]) -> None:
    """Commit one validated file set under the project-wide write lock."""
    if not writes:
        return
    with formal_write_lock():
        _write_transaction_unlocked(writes)
