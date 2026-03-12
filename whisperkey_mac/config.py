from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path


CONFIG_PATH = Path.home() / ".config" / "whisperkey" / "config.json"


@dataclass
class AppConfig:
    # ── UI ────────────────────────────────────────────────────────────────────
    # Interface language: "zh" | "en"
    ui_language: str = "zh"

    # ── Transcription ─────────────────────────────────────────────────────────
    # Language passed to Whisper: None = auto-detect, "zh", "en", ISO code
    language: str | None = None
    # Human-readable label stored in config: "auto" | "zh" | "en" | ISO code
    transcribe_language: str = "auto"

    # ── Whisper model ─────────────────────────────────────────────────────────
    model_size: str = "small"
    compute_type: str = "int8"
    device: str = "cpu"

    # ── Audio ─────────────────────────────────────────────────────────────────
    sample_rate: int = 16000
    min_duration_s: float = 0.3
    temp_dir: Path = field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "whisperkey_mac"
    )

    # ── Hotkeys ───────────────────────────────────────────────────────────────
    # pynput Key name for hold-to-talk (press & hold → record, release → transcribe)
    hold_key: str = "alt_r"
    # pynput Key names for hands-free combo (both held simultaneously → toggle)
    handsfree_keys: list = field(default_factory=lambda: ["alt_r", "cmd_r"])

    # ── Output ────────────────────────────────────────────────────────────────
    auto_paste: bool = True
    result_max_lines: int = 3
    online_correct_enabled: bool = False
    online_correct_provider: str = "openai"
    online_correct_model: str = "gpt-5-mini"
    online_correct_timeout_s: float = 2.0
    online_correct_min_chars: int = 6
    online_correct_max_chars: int = 120
    online_correct_min_cjk_ratio: float = 0.35

    # ── Legacy ────────────────────────────────────────────────────────────────
    record_button: str = "x1"
    enter_button: str = "x2"
    enter_mode: str = "enter"
    record_hotkey: str = ""
    enter_hotkey: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["temp_dir"] = str(self.temp_dir)
        return d


def _transcribe_language_to_whisper(code: str) -> str | None:
    if code in ("auto", ""):
        return None
    return code


def load_config() -> AppConfig:
    cfg = AppConfig()

    # 1. Load from JSON if it exists
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            for k, v in data.items():
                if hasattr(cfg, k):
                    if k == "temp_dir":
                        object.__setattr__(cfg, k, Path(v))
                    else:
                        object.__setattr__(cfg, k, v)
        except Exception:
            pass

    # 2. Env var overrides
    if v := os.getenv("WHISPERKEY_MODEL"):
        cfg.model_size = v
    if v := os.getenv("WHISPERKEY_COMPUTE_TYPE"):
        cfg.compute_type = v
    if v := os.getenv("WHISPERKEY_DEVICE"):
        cfg.device = v
    if v := os.getenv("WHISPERKEY_LANGUAGE"):
        cfg.language = v or None
    if v := os.getenv("WHISPERKEY_SAMPLE_RATE"):
        cfg.sample_rate = int(v)
    if v := os.getenv("WHISPERKEY_TEMP_DIR"):
        cfg.temp_dir = Path(v) / "whisperkey_mac"
    if v := os.getenv("WHISPERKEY_MIN_DURATION"):
        cfg.min_duration_s = float(v)
    if v := os.getenv("WHISPERKEY_AUTO_PASTE"):
        cfg.auto_paste = v == "1"
    if v := os.getenv("WHISPERKEY_RESULT_MAX_LINES"):
        cfg.result_max_lines = max(1, int(v))
    if v := os.getenv("WHISPERKEY_ONLINE_CORRECT"):
        cfg.online_correct_enabled = v.strip().lower() in {"1", "true", "yes", "on"}
    if v := os.getenv("WHISPERKEY_ONLINE_CORRECT_MODEL"):
        cfg.online_correct_model = v.strip()

    # Sync transcribe_language → Whisper language param (if not set by env var)
    if cfg.language is None and cfg.transcribe_language != "auto":
        cfg.language = _transcribe_language_to_whisper(cfg.transcribe_language)

    return cfg


def save_config(cfg: AppConfig) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False))


def config_exists() -> bool:
    return CONFIG_PATH.exists()
