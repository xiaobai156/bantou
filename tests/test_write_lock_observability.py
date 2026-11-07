# -*- coding: utf-8 -*-
"""正式输出锁：句柄不可继承、占用者可观测、超时报文可定位。"""
from __future__ import annotations

import msvcrt
import os
import time

import pytest

from bantou.application import single_period
from bantou.outputs import transaction


def test_lock_handle_is_not_inheritable():
    """可继承句柄会被 spawn 子进程带走，父进程退出后锁仍被占。"""
    handle = transaction._open_lock_handle()
    try:
        assert os.get_inheritable(handle.fileno()) is False
        assert os.get_handle_inheritable(msvcrt.get_osfhandle(handle.fileno())) is False
    finally:
        handle.close()


def test_lock_owner_written_on_acquire_and_cleared_on_release(monkeypatch, tmp_path):
    owner = tmp_path / "lock.owner"
    monkeypatch.setattr(transaction, "_OWNER_PATH", owner)

    with transaction.formal_write_lock():
        assert owner.exists()
        pid, started = owner.read_text(encoding="utf-8").strip().split("\t")
        assert pid == str(os.getpid())
        assert started.startswith("20")

    assert not owner.exists()
    assert transaction._read_lock_owner() == ""


def test_lock_timeout_reports_holder_pid_and_time(monkeypatch, tmp_path):
    owner = tmp_path / "lock.owner"
    owner.write_text("4321\t2026-11-06T21:33:07+08:00\n", encoding="utf-8")
    monkeypatch.setattr(transaction, "_OWNER_PATH", owner)
    monkeypatch.setattr(transaction, "LOCK_WAIT_SECONDS", 0)

    def always_locked(*args, **kwargs):
        raise OSError("locked by another process")

    monkeypatch.setattr(transaction.msvcrt, "locking", always_locked)
    handle = transaction._open_lock_handle()
    try:
        with pytest.raises(TimeoutError) as excinfo:
            transaction._lock_handle(handle)
    finally:
        handle.close()

    message = str(excinfo.value)
    assert "等待正式输出锁超过0秒" in message
    assert "pid=4321" in message
    assert "2026-11-06T21:33:07" in message


def test_lock_timeout_without_owner_stays_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(transaction, "_OWNER_PATH", tmp_path / "missing.owner")
    monkeypatch.setattr(transaction, "LOCK_WAIT_SECONDS", 0)

    def always_locked(*args, **kwargs):
        raise OSError("locked by another process")

    monkeypatch.setattr(transaction.msvcrt, "locking", always_locked)
    handle = transaction._open_lock_handle()
    try:
        with pytest.raises(TimeoutError, match="占用者未知"):
            transaction._lock_handle(handle)
    finally:
        handle.close()


def test_reap_without_children_is_bounded_and_empty():
    started = time.monotonic()
    reaped = single_period._reap_spawn_children(time.monotonic() + 0.5)
    assert reaped == 0
    assert time.monotonic() - started < 1.0
