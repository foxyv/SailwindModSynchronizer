from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import POINTER, HRESULT, byref, c_void_p, wintypes

from sailwind_mod_sync.constants import APP_USER_MODEL_ID

log = logging.getLogger(__name__)

CLSCTX_INPROC_SERVER = 0x1


def clear_jump_list() -> None:
    """Remove a previously published taskbar Jump List so stale tasks disappear."""
    if sys.platform != "win32":
        return
    dest = None
    try:
        dest = _create_instance(
            _guid("{77f10cf0-3db5-4966-b520-b7c54fd35ed6}"),
            _guid("{6332debf-87b5-4670-90c0-5e57b408a49e}"),
        )
        _check(_method(dest, 3, HRESULT, [wintypes.LPCWSTR])(APP_USER_MODEL_ID), "SetAppID")
        _check(_method(dest, 10, HRESULT, [wintypes.LPCWSTR])(APP_USER_MODEL_ID), "DeleteList")
    except OSError as exc:
        log.debug("Could not clear taskbar Jump List: %s", exc)
    finally:
        _release(dest)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(value: str) -> _GUID:
    ole32 = ctypes.WinDLL("ole32")
    ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, POINTER(_GUID)]
    ole32.CLSIDFromString.restype = HRESULT
    parsed = _GUID()
    _check(ole32.CLSIDFromString(value, byref(parsed)), f"CLSIDFromString({value})")
    return parsed


def _vtable(ptr: int):
    return ctypes.cast(c_void_p(ptr), POINTER(POINTER(c_void_p))).contents


def _method(ptr: int, index: int, restype, argtypes):
    func = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(_vtable(ptr)[index])

    def _call(*args):
        return func(ptr, *args)

    return _call


def _check(hr: int, what: str) -> None:
    if hr:
        raise OSError(f"{what} failed: 0x{hr & 0xFFFFFFFF:08X}")


def _create_instance(clsid: _GUID, iid: _GUID) -> int:
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoCreateInstance.argtypes = [
        POINTER(_GUID),
        c_void_p,
        wintypes.DWORD,
        POINTER(_GUID),
        POINTER(c_void_p),
    ]
    ole32.CoCreateInstance.restype = HRESULT
    ptr = c_void_p()
    _check(
        ole32.CoCreateInstance(byref(clsid), None, CLSCTX_INPROC_SERVER, byref(iid), byref(ptr)),
        "CoCreateInstance",
    )
    if not ptr.value:
        raise OSError("CoCreateInstance returned a null pointer")
    return int(ptr.value)


def _release(ptr: int | None) -> None:
    if not ptr:
        return
    _method(ptr, 2, wintypes.ULONG, [])()
