"""Tests for the macOS main-thread TIS patch (pynput crash fix on macOS 26).

The patch reads the keyboard layout once at startup and then replaces pynput's
``keycode_context`` so it never calls the Text Input Source APIs off the main
thread again. We stub the real ``keycode_context`` so these tests are
deterministic and never touch real Carbon/TIS state.
"""

from __future__ import annotations

import contextlib

import pytest

import whisperkey_mac.pynput_mainthread_patch as patch_mod


@pytest.fixture(autouse=True)
def _reset_applied():
    patch_mod._applied = False
    yield
    patch_mod._applied = False


def _install_fake_pynput(monkeypatch, sentinel):
    """Replace the real TIS-backed keycode_context with a counting fake."""
    pd = pytest.importorskip("pynput._util.darwin")
    kd = pytest.importorskip("pynput.keyboard._darwin")

    calls = {"n": 0}

    @contextlib.contextmanager
    def fake_real_context():
        calls["n"] += 1
        yield sentinel

    monkeypatch.setattr(pd, "keycode_context", fake_real_context)
    monkeypatch.setattr(kd, "keycode_context", fake_real_context)
    return pd, kd, calls


def test_patch_caches_layout_and_replaces_both_namespaces(monkeypatch):
    monkeypatch.setattr(patch_mod.sys, "platform", "darwin")
    sentinel = ("kbtype", b"layout")
    pd, kd, calls = _install_fake_pynput(monkeypatch, sentinel)

    assert patch_mod.apply_pynput_mainthread_patch() is True
    # The real layout reader is invoked exactly once (the main-thread warm-up).
    assert calls["n"] == 1
    # Both namespaces now resolve to the cached context manager.
    assert pd.keycode_context is kd.keycode_context
    assert pd.keycode_context.__name__ == "_cached_keycode_context"

    # Every subsequent use yields the cached value without touching TIS again —
    # this is what makes the background listener thread safe on macOS 26.
    with pd.keycode_context() as ctx:
        assert ctx == sentinel
    with kd.keycode_context() as ctx:
        assert ctx == sentinel
    assert calls["n"] == 1


def test_patch_is_idempotent(monkeypatch):
    monkeypatch.setattr(patch_mod.sys, "platform", "darwin")
    sentinel = ("kbtype", b"layout")
    pd, _kd, calls = _install_fake_pynput(monkeypatch, sentinel)

    assert patch_mod.apply_pynput_mainthread_patch() is True
    first = pd.keycode_context
    assert patch_mod.apply_pynput_mainthread_patch() is True
    # Second call is a no-op: no re-read, no re-wrap.
    assert pd.keycode_context is first
    assert calls["n"] == 1


def test_patch_noop_off_darwin(monkeypatch):
    monkeypatch.setattr(patch_mod.sys, "platform", "linux")
    assert patch_mod.apply_pynput_mainthread_patch() is False
