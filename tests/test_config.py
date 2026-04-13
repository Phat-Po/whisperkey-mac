from whisperkey_mac.config import AppConfig


def test_online_prompt_mode_defaults_disabled():
    cfg = AppConfig()
    assert cfg.online_prompt_mode == "disabled"
    assert cfg.launch_at_login is False


def test_online_prompt_mode_can_represent_custom_prompt():
    cfg = AppConfig(
        online_prompt_mode="custom",
        online_prompt_custom_text="Translate to English",
    )
    assert cfg.online_prompt_mode == "custom"
    assert cfg.online_prompt_custom_text == "Translate to English"
