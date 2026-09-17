from __future__ import annotations

from sailwind_mod_sync.ui.windows_shell import clear_jump_list


def test_clear_jump_list_does_not_raise() -> None:
    clear_jump_list()
