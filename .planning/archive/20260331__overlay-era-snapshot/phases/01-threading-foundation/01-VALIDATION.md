---
phase: 1
slug: threading-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest — NOT YET INSTALLED |
| **Config file** | None — Wave 0 installs |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v` + full manual smoke test checklist
- **Before `/gsd:verify-work`:** Full suite must be green + manual smoke checklist complete
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | OVL-02 | Manual smoke | Manual — press hotkey, speak, release, confirm transcription appears | N/A | ⬜ pending |
| 1-01-02 | 01 | 1 | OVL-02 | Manual smoke | Manual — Ctrl+C, confirm `[whisperkey] shutting down (SIGINT)` printed | N/A | ⬜ pending |
| 1-02-01 | 02 | 2 | OVL-01 | Unit | `pytest tests/test_overlay.py::test_panel_flags -x` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 2 | OVL-01 | Unit | `pytest tests/test_overlay.py::test_panel_position -x` | ❌ W0 | ⬜ pending |
| 1-02-03 | 02 | 2 | OVL-01 | Unit | `pytest tests/test_overlay.py::test_panel_invisible -x` | ❌ W0 | ⬜ pending |
| 1-02-04 | 02 | 2 | OVL-02 | Unit | `pytest tests/test_overlay.py::test_activation_policy -x` | ❌ W0 | ⬜ pending |
| 1-02-05 | 02 | 2 | OVL-02 | Manual smoke | Manual — start WhisperKey, type in TextEdit, confirm no focus steal | N/A | ⬜ pending |
| 1-02-06 | 02 | 2 | OVL-03 | Unit | `pytest tests/test_overlay.py::test_collection_behavior -x` | ❌ W0 | ⬜ pending |
| 1-02-07 | 02 | 2 | OVL-03 | Unit | `pytest tests/test_overlay.py::test_dispatch_to_main -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — empty file to make tests a package
- [ ] `tests/conftest.py` — shared fixtures (NSApplication.sharedApplication() setup)
- [ ] `tests/test_overlay.py` — unit tests for NSPanel flag verification (OVL-01, OVL-02, OVL-03 structural checks)
- [ ] Framework install: add `pytest>=7.0` to `pyproject.toml` dependencies

Note: Unit tests for NSPanel flags work WITHOUT a running NSApp run loop — NSPanel can be created and introspected in a test process since creating an NSPanel does not require `NSApp.run()` to be active.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hotkey press → speak → release → text appears | OVL-02 (thread survival) | Requires real audio hardware and live transcription service | Start WhisperKey, press hotkey, speak a sentence, release key, confirm transcription appears in active window |
| Focus-steal: TextEdit keeps focus when WhisperKey starts | OVL-02 | Requires visual inspection of window focus state | Open TextEdit, position cursor, start WhisperKey, confirm TextEdit cursor is still active |
| Ctrl+C prints shutdown message | OVL-02 | Requires interactive terminal session | Run WhisperKey, press Ctrl+C, confirm `[whisperkey] shutting down (SIGINT)` printed |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
