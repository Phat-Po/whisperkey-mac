"""AX cursor detection module for WhisperKey macOS.

Provides:
- is_cursor_in_text_field(): returns True if the currently focused macOS UI element
  is a text input field (AXTextField, AXTextArea, AXComboBox, AXSearchField).

Thread-safe: AXUIElement APIs are safe to call from non-main threads.
Failure-safe: any exception or AX error returns False (DET-02 safe-degradation).

IMPORTANT: macOS requires Accessibility permission (System Settings -> Privacy & Security ->
Accessibility) for this to return True. If permission is denied, kAXErrorAPIDisabled (-25211)
is returned and this function returns False, falling back to the clipboard path. This is
correct per DET-02 — no crash, just clipboard-path degradation.

NOTE: kAXSearchFieldRole does NOT exist as an importable constant in PyObjC 12.1.
The package exports kAXSearchFieldSubrole with the same value 'AXSearchField'.
The string literal 'AXSearchField' is used directly in _TEXT_INPUT_ROLES instead.
"""
from ApplicationServices import (
    AXUIElementCreateSystemWide,
    AXUIElementCopyAttributeValue,
    AXUIElementSetAttributeValue,
    AXValueCreate,
    AXValueGetValue,
    kAXEnabledAttribute,           # 'AXEnabled'
    kAXFocusedUIElementAttribute,  # 'AXFocusedUIElement'
    kAXSelectedTextRangeAttribute, # 'AXSelectedTextRange'
    kAXRoleAttribute,              # 'AXRole'
    kAXTextFieldRole,              # 'AXTextField'
    kAXTextAreaRole,               # 'AXTextArea'
    kAXComboBoxRole,               # 'AXComboBox'
    kAXValueAttribute,             # 'AXValue'
    kAXValueCFRangeType,           # 4
    kAXErrorSuccess,               # 0
    # NOTE: kAXSearchFieldRole does NOT exist — verified ImportError in .venv Python 3.12 + PyObjC 12.1
    # kAXSearchFieldSubrole == 'AXSearchField'; use string literal directly
)

_TEXT_INPUT_ROLES: frozenset[str] = frozenset({
    kAXTextFieldRole,   # 'AXTextField'
    kAXTextAreaRole,    # 'AXTextArea'
    kAXComboBoxRole,    # 'AXComboBox'
    "AXSearchField",    # kAXSearchFieldRole doesn't exist; kAXSearchFieldSubrole == 'AXSearchField'
})

_AX_EDITABLE_ATTRIBUTE = "AXEditable"


def _get_ax_value(element, attribute: str):
    err, value = AXUIElementCopyAttributeValue(element, attribute, None)
    if err != kAXErrorSuccess:
        return None
    return value


def _set_ax_value(element, attribute: str, value) -> bool:
    return AXUIElementSetAttributeValue(element, attribute, value) == kAXErrorSuccess


def _is_editable_text_input(element) -> bool:
    role = _get_ax_value(element, kAXRoleAttribute)
    if role is None or role not in _TEXT_INPUT_ROLES:
        return False
    enabled = _get_ax_value(element, kAXEnabledAttribute)
    editable = _get_ax_value(element, _AX_EDITABLE_ATTRIBUTE)
    return enabled is True and editable is True


def _focused_text_input_element():
    system_wide = AXUIElementCreateSystemWide()
    focused = _get_ax_value(system_wide, kAXFocusedUIElementAttribute)
    if focused is None:
        return None
    return focused if _is_editable_text_input(focused) else None


def _get_selected_range(element) -> tuple[int, int] | None:
    range_value = _get_ax_value(element, kAXSelectedTextRangeAttribute)
    if range_value is None:
        return None
    ok, value = AXValueGetValue(range_value, kAXValueCFRangeType, None)
    if not ok or not isinstance(value, tuple) or len(value) != 2:
        return None
    location, length = value
    if not isinstance(location, int) or not isinstance(length, int):
        return None
    return location, length


def insert_text_at_cursor(text: str) -> bool:
    """Insert text into the focused editable AX text element.

    Uses AXValue + AXSelectedTextRange to splice text at the current cursor/selection.
    Returns False on any AX failure so callers can safely fall back to clipboard paste.
    """
    if not text:
        return False

    try:
        focused = _focused_text_input_element()
        if focused is None:
            return False

        current_value = _get_ax_value(focused, kAXValueAttribute)
        selected_range = _get_selected_range(focused)
        if not isinstance(current_value, str) or selected_range is None:
            return False

        location, length = selected_range
        if location < 0 or length < 0 or location > len(current_value):
            return False
        end = location + length
        if end > len(current_value):
            return False

        updated_value = current_value[:location] + text + current_value[end:]
        if not _set_ax_value(focused, kAXValueAttribute, updated_value):
            return False

        next_range = AXValueCreate(kAXValueCFRangeType, (location + len(text), 0))
        _set_ax_value(focused, kAXSelectedTextRangeAttribute, next_range)
        return True
    except Exception:
        return False


def is_cursor_in_text_field() -> bool:
    """Return True if the currently focused macOS UI element is a text input field.

    Thread-safe: AXUIElement APIs are designed for non-main-thread use.
    Failure-safe: any exception or AX error returns False (DET-02 safe-degradation).

    Returns:
        True if focused element role is AXTextField, AXTextArea, AXComboBox, or AXSearchField.
        False on any error, permission denial, exception, or non-text role.
    """
    try:
        return _focused_text_input_element() is not None
    except Exception:
        return False  # DET-02: any failure -> clipboard path (safe degradation)
