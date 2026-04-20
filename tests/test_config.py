import json

from whisperkey_mac import config as config_module
from whisperkey_mac.config import AppConfig, load_config, save_config


def test_online_prompt_mode_defaults_disabled():
    cfg = AppConfig()
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
    assert data["mode_cycle_keys"] == ["cmd", "shift", "char:m"]
    assert data["mode_cycle_targets"] == ["disabled", "voice_cleanup"]
