---
phase: 2
slug: state-machine-thread-wiring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 (already installed) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 0 | RST-01, RST-02 | unit | `pytest tests/test_overlay.py::test_hide_after_paste -x` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 0 | RST-02, RST-03 | unit | `pytest tests/test_overlay.py::test_show_result_sets_label -x` | ❌ W0 | ⬜ pending |
| 2-01-03 | 01 | 0 | RST-03 | unit | `pytest tests/test_overlay.py::test_show_result_clipboard_hint -x` | ❌ W0 | ⬜ pending |
| 2-01-04 | 01 | 0 | RST-04 | unit | `pytest tests/test_overlay.py::test_auto_dismiss_fires -x` | ❌ W0 | ⬜ pending |
| 2-01-05 | 01 | 0 | RST-04 | unit | `pytest tests/test_overlay.py::test_auto_dismiss_stale_ignored -x` | ❌ W0 | ⬜ pending |
| 2-01-06 | 01 | 0 | RST-01 | unit | `pytest tests/test_overlay.py::test_transition_guard_rejects_invalid -x` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02 | 0 | DET-01 | unit (mocked) | `pytest tests/test_ax_detect.py::test_text_input_roles -x` | ❌ W0 | ⬜ pending |
| 2-02-02 | 02 | 0 | DET-01 | unit (mocked) | `pytest tests/test_ax_detect.py::test_non_text_roles -x` | ❌ W0 | ⬜ pending |
| 2-02-03 | 02 | 0 | DET-02 | unit (mocked) | `pytest tests/test_ax_detect.py::test_ax_error_returns_false -x` | ❌ W0 | ⬜ pending |
| 2-02-04 | 02 | 0 | DET-02 | unit (mocked) | `pytest tests/test_ax_detect.py::test_ax_exception_returns_false -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_overlay.py` — extend with state machine transition tests (RST-01 through RST-04, state guard)
- [ ] `tests/test_ax_detect.py` — CREATE: mock-based unit tests for `ax_detect.is_cursor_in_text_field()` (DET-01, DET-02)

*Existing infrastructure — conftest.py, NSApplication setup, pytest config — already covers Phase 2 needs; no new fixtures required.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Press hotkey → overlay appears; release → "转录中..." visible; result → clipboard text + "已复制到剪贴板" shows; auto-dismisses after 3s | RST-02, RST-03, RST-04 | Requires real macOS UI + audio | Run app, press/hold hotkey, speak, release; verify overlay sequence |
| Cursor in TextEdit → transcription pastes silently, overlay hides within 200ms | RST-01 | Requires Accessibility permission + real text input | Open TextEdit, click in body, hold hotkey, speak, release; verify paste without overlay result |
| Press hotkey, release, press again before transcription completes → second press has no visible effect | RST-01 (state guard) | Requires real concurrency | Press, release, immediately press again; verify overlay stays in transcribing state |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
