"""DLL identity helpers shared by plugin scanning and library extraction."""

from __future__ import annotations

import re
from pathlib import Path

# GUID prefixes of framework/system assemblies, used to filter dependency DLLs.
SKIP_GUID_PREFIXES = (
    "system.",
    "unityengine.",
    "unity.",
    "harmony",
    "bepinex.",
    "microsoft.",
    "mono.",
    "mscorlib",
    "netstandard",
    "newtonsoft.",
    "assembly-csharp",
)
_SKIP_STEMS = frozenset({"mscorlib", "netstandard", "assembly-csharp"})
_SKIP_PREFIXES = tuple(p.rstrip(".") for p in SKIP_GUID_PREFIXES)
_BEPINEX_BYTES = b"BepInEx"

# Generic container folder names that don't identify a specific mod.
GENERIC_FOLDER_NAMES = frozenset({"", ".", "plugin", "plugins", "mod", "mods"})


def is_generic_folder_name(name: str) -> bool:
    """True if *name* is a generic container word, not a meaningful mod identifier."""
    return name.strip().lower() in GENERIC_FOLDER_NAMES


def _is_dependency_dll(dll_path: Path) -> bool:
    """True if DLL stem matches known dependency patterns."""
    stem_lower = dll_path.stem.lower()
    return stem_lower in _SKIP_STEMS or any(
        stem_lower.startswith(p) for p in _SKIP_PREFIXES
    )


def _references_bepinex(dll_path: Path) -> bool:
    """True if the DLL binary contains 'BepInEx' (the modding framework)."""
    try:
        data = dll_path.read_bytes()
    except OSError:
        return False
    return _BEPINEX_BYTES in data


def _tokens(value: str) -> set[str]:
    parts = re.findall(r"[A-Z]?[a-z]+|[0-9]+", value)
    if not parts:
        parts = re.findall(r"[a-z0-9]+", value.lower())
    skip = {"the", "a", "an", "in", "of", "and", "hms", "sailwind", "mod", "plugin"}
    return {part.lower() for part in parts if part.lower() not in skip}


def pick_main_dll(
    dlls: list[Path],
    *,
    hints: tuple[str, ...] = (),
) -> Path | None:
    """Select the main mod DLL when a folder contains multiple DLLs.

    Three-step hierarchical filter:
      1. Remove dependency DLLs by name pattern (SKIP_GUID_PREFIXES).
      2. Check binaries for BepInEx reference — the modding framework
         that 99% of mods load through.
      3. Token-overlap matching against hint names (folder, repo, archive).

    Falls back to the first DLL in name-sorted (alphabetical) order.
    """
    if not dlls:
        return None
    if len(dlls) == 1:
        return dlls[0]

    # Step 1: filter dependency DLLs by name pattern
    non_dep = [d for d in dlls if not _is_dependency_dll(d)]
    if len(non_dep) == 1:
        return non_dep[0]
    if not non_dep:
        # Every DLL looks like a dependency — name-sorted fallback on the originals.
        return sorted(dlls, key=lambda p: p.stem.lower())[0]

    # Step 2: BepInEx binary reference check
    bepinex_dlls = [d for d in non_dep if _references_bepinex(d)]
    if len(bepinex_dlls) == 1:
        return bepinex_dlls[0]

    # Step 3: token overlap with hints
    candidates = bepinex_dlls or non_dep
    if hints:
        hint_tokens: set[str] = set()
        for h in hints:
            hint_tokens |= _tokens(h)
        if hint_tokens:
            best_count = -1
            best_dlls: list[Path] = []
            for dll in candidates:
                dll_tokens = _tokens(dll.stem)
                count = len(dll_tokens & hint_tokens)
                if count > best_count:
                    best_count = count
                    best_dlls = [dll]
                elif count == best_count:
                    best_dlls.append(dll)
            if best_count > 0:
                return sorted(best_dlls, key=lambda p: p.stem.lower())[0]

    # Fallback: first in name-sorted order
    return sorted(candidates, key=lambda p: p.stem.lower())[0]
