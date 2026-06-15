import json

from whisperkey_mac import config as config_module
from whisperkey_mac.config import AppConfig, load_config, save_config


def test_online_prompt_mode_defaults_disabled():
    cfg = AppConfig()
    assert cfg.asr_engine == "local"
    assert cfg.online_prompt_mode == "disabled"
    assert cfg.launch_at_login is False
    assert cfg.mode_cycle_keys == []
    assert cfg.mode_cycle_targets == ["asr_correction", "voice_cleanup"]


def test_online_prompt_mode_can_represent_custom_prompt():
    cfg = AppConfig(
        online_prompt_mode="custom",
        online_prompt_custom_text="Translate to English",
    )
    assert cfg.online_prompt_mode == "custom"
    assert cfg.online_prompt_custom_text == "Translate to English"


def test_load_config_validates_mode_cycle_fields(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "mode_cycle_keys": "cmd, char:m",
                "mode_cycle_targets": ["custom", "unknown"],
            }
        )
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    cfg = load_config()

    assert cfg.mode_cycle_keys == []
    assert cfg.mode_cycle_targets == ["asr_correction", "voice_cleanup"]


def test_load_config_migrates_legacy_streaming_mode_to_asr_engine(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"online_prompt_mode": "streaming"}))
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    cfg = load_config()

    assert cfg.asr_engine == "doubao"
    assert cfg.online_prompt_mode == "voice_cleanup"
    assert cfg.online_correct_enabled is True


def test_load_config_rejects_unknown_asr_engine(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"asr_engine": "unknown"}))
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    cfg = load_config()

    assert cfg.asr_engine == "local"


def test_save_config_persists_mode_cycle_fields(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    save_config(
        AppConfig(
            mode_cycle_keys=["cmd", "shift", "char:m"],
            mode_cycle_targets=["disabled", "voice_cleanup"],
        )
    )

    data = json.loads(config_path.read_text())
    assert data["asr_engine"] == "local"
    assert data["mode_cycle_keys"] == ["cmd", "shift", "char:m"]
    assert data["mode_cycle_targets"] == ["disabled", "voice_cleanup"]


def test_load_config_ignores_malformed_numeric_env_vars(monkeypatch):
    monkeypatch.setenv("WHISPERKEY_SAMPLE_RATE", "not-a-number")
    monkeypatch.setenv("WHISPERKEY_MIN_DURATION", "abc")
    monkeypatch.setenv("WHISPERKEY_RESULT_MAX_LINES", "")

    from whisperkey_mac.config import load_config

    cfg = load_config()

    assert cfg.sample_rate == 16000
    assert cfg.min_duration_s == 0.3
