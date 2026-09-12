from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

GW_OWNER = 4
MIN_WINDOW_WIDTH = 200
MIN_WINDOW_HEIGHT = 120


def process_has_visible_window(
    pid: int,
    *,
    min_width: int = MIN_WINDOW_WIDTH,
    min_height: int = MIN_WINDOW_HEIGHT,
) -> bool:
    """True when pid has a visible, owned-by-itself window of a useful size."""
    if os.name != "nt" or pid <= 0:
        return False
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        proc = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        if proc.value != pid:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width >= min_width and height >= min_height:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(callback, 0)
    return bool(found)
