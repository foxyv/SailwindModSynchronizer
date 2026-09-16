from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from sailwind_mod_sync.constants import GAME_EXE_NAME

GW_OWNER = 4
MIN_WINDOW_WIDTH = 200
MIN_WINDOW_HEIGHT = 120


def process_image_name(pid: int) -> str | None:
    """Basename of the executable for pid (e.g. 'Sailwind.exe'), or None when unknown."""
    if os.name != "nt" or pid <= 0:
        return None
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return None
    try:
        size = wintypes.DWORD(264)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(process, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return None
    finally:
        kernel32.CloseHandle(process)


def sailwind_window_visible(
    *,
    min_width: int = MIN_WINDOW_WIDTH,
    min_height: int = MIN_WINDOW_HEIGHT,
) -> bool:
    """True when a visible Sailwind.exe window of a useful size is on screen.

    Used when the game was handed off to Steam, so we have no pid to track and
    must recognize the game by its window instead.
    """
    return window_exists_for_image(GAME_EXE_NAME, min_width=min_width, min_height=min_height)


def window_exists_for_image(
    image_name: str,
    *,
    min_width: int = MIN_WINDOW_WIDTH,
    min_height: int = MIN_WINDOW_HEIGHT,
) -> bool:
    """True when some top-level visible window belongs to a process with this exe name."""
    if os.name != "nt":
        return False
    target = image_name.lower()
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        proc = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        name = process_image_name(proc.value)
        if not name or name.lower() != target:
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
