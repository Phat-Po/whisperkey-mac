from whisperkey_mac.settings_window import parse_shortcut_list, shortcut_list_to_text


def test_parse_shortcut_list_trims_and_filters_empty_entries():
    assert parse_shortcut_list(" alt_r, cmd_r , , shift ") == ["alt_r", "cmd_r", "shift"]


def test_shortcut_list_to_text_formats_for_field_display():
    assert shortcut_list_to_text(["alt_r", "cmd_r"]) == "alt_r, cmd_r"
