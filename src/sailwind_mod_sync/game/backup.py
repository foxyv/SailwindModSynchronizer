from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sailwind_mod_sync.http_util import ProgressFn

PRELOADER = "core/bepinex.preloader.dll"


class BackupError(ValueError):
    pass


@dataclass
class BackupResult:
    dest: Path
    source: Path
    file_count: int
    skipped: int


@dataclass
class RestoreResult:
    dest: Path
    archive: Path
    file_count: int


def backup_bepinex_folder(source: Path, dest: Path, progress: ProgressFn | None = None) -> BackupResult:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"BepInEx folder not found: {source}")
    files = [path for path in source.rglob("*") if path.is_file()]
    if not files:
        raise FileNotFoundError(f"BepInEx folder is empty: {source}")
    return zip_folder(source, dest, files, progress=progress)


def zip_folder(
    source: Path,
    dest: Path,
    files: list[Path],
    progress: ProgressFn | None = None,
) -> BackupResult:
    source = source.resolve()
    dest = dest.resolve()
    if dest.suffix.lower() != ".zip":
        dest = dest.with_suffix(".zip")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    skipped = 0
    written = 0
    total = len(files)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                rel = path.relative_to(source).as_posix()
                arcname = f"{source.name}/{rel}"
                if progress:
                    progress(f"Backing up {rel} ({written + skipped + 1}/{total})")
                try:
                    archive.write(path, arcname)
                    written += 1
                except OSError:
                    skipped += 1
        if written == 0:
            raise RuntimeError(f"Could not read any files from {source}")
        tmp.replace(dest)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    return BackupResult(dest=dest, source=source, file_count=written, skipped=skipped)


def inspect_bepinex_zip(archive: Path) -> str:
    """Return the zip prefix of the BepInEx folder ('' if the zip root is the folder)."""
    names = _zip_file_names(archive)
    for prefix in _candidate_prefixes(names):
        if _prefix_looks_like_bepinex(names, prefix, require_named_root=True):
            return prefix
    if _prefix_looks_like_bepinex(names, "", require_named_root=False):
        return ""
    raise BackupError(
        "This zip is not a BepInEx backup. It needs a BepInEx folder with plugins (DLL files) "
        "and/or core/BepInEx.Preloader.dll."
    )


def is_valid_bepinex_directory(path: Path) -> bool:
    if not path.is_dir():
        return False
    has_preloader = (path / "core" / "BepInEx.Preloader.dll").is_file()
    plugins = path / "plugins"
    has_plugin_dll = plugins.is_dir() and any(plugins.rglob("*.dll"))
    return has_preloader or has_plugin_dll


def restore_bepinex_folder(
    archive: Path,
    dest: Path,
    progress: ProgressFn | None = None,
) -> RestoreResult:
    archive = archive.resolve()
    dest = dest.resolve()
    if progress:
        progress("Checking backup zip…")
    prefix = inspect_bepinex_zip(archive)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f"{dest.name}.restore-tmp"
    old = dest.parent / f"{dest.name}.restore-old"
    _remove_tree(tmp)
    tmp.mkdir(parents=True)
    try:
        if progress:
            progress("Extracting backup…")
        count = _extract_prefix(archive, tmp, prefix, progress)
        if not is_valid_bepinex_directory(tmp):
            raise BackupError(
                "The extracted files are not a valid BepInEx directory "
                "(need plugins with DLLs or core/BepInEx.Preloader.dll)."
            )
        if progress:
            progress(f"Replacing {dest}…")
        _remove_tree(old)
        try:
            if dest.exists():
                dest.rename(old)
            tmp.rename(dest)
        except OSError as exc:
            if not dest.exists() and old.exists():
                old.rename(dest)
            raise BackupError(
                f"Could not replace {dest}. Close Sailwind and try again. ({exc})"
            ) from exc
        _remove_tree(old)
    except Exception:
        _remove_tree(tmp)
        raise
    return RestoreResult(dest=dest, archive=archive, file_count=count)


def _zip_file_names(archive: Path) -> list[str]:
    if not archive.is_file():
        raise BackupError(f"Backup not found: {archive}")
    if not zipfile.is_zipfile(archive):
        raise BackupError("That file is not a zip archive.")
    names: list[str] = []
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/").lstrip("/")
            if not name or name.endswith("/"):
                continue
            if ".." in Path(name).parts:
                raise BackupError(f"Unsafe zip path: {info.filename}")
            names.append(name)
    if not names:
        raise BackupError("Zip archive is empty.")
    return names


def _candidate_prefixes(names: list[str]) -> list[str]:
    found: set[str] = set()
    for name in names:
        parts = name.split("/")
        for index, part in enumerate(parts[:-1]):
            if part.lower() == "bepinex":
                found.add("/".join(parts[: index + 1]))
    return sorted(found, key=lambda item: (item.count("/"), item.lower()))


def _prefix_looks_like_bepinex(names: list[str], prefix: str, *, require_named_root: bool) -> bool:
    pfx = prefix.rstrip("/") + "/" if prefix else ""
    has_preloader = False
    has_plugin_dll = False
    has_config = False
    for name in names:
        if pfx and not name.startswith(pfx):
            continue
        rel = name[len(pfx) :] if pfx else name
        if not rel:
            continue
        lower = rel.lower()
        if lower == PRELOADER:
            has_preloader = True
        elif lower.startswith("plugins/") and lower.endswith(".dll"):
            has_plugin_dll = True
        elif lower.startswith("config/"):
            has_config = True
    if require_named_root:
        return has_preloader or has_plugin_dll
    return has_preloader or (has_plugin_dll and has_config)


def _extract_prefix(
    archive: Path,
    dest: Path,
    prefix: str,
    progress: ProgressFn | None,
) -> int:
    dest = dest.resolve()
    pfx = prefix.rstrip("/") + "/" if prefix else ""
    written = 0
    with zipfile.ZipFile(archive) as zf:
        members = [
            info
            for info in zf.infolist()
            if not info.is_dir() and _member_under_prefix(info.filename, pfx)
        ]
        total = len(members)
        for info in members:
            name = info.filename.replace("\\", "/").lstrip("/")
            rel = name[len(pfx) :] if pfx else name
            if not rel:
                continue
            target = (dest / rel).resolve()
            if not target.is_relative_to(dest):
                raise BackupError(f"Unsafe zip path: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if progress:
                progress(f"Restoring {rel} ({written + 1}/{total})")
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
            written += 1
    if written == 0:
        raise BackupError("Backup zip had no files to restore.")
    return written


def _member_under_prefix(filename: str, pfx: str) -> bool:
    name = filename.replace("\\", "/").lstrip("/")
    if name.endswith("/"):
        return False
    if not pfx:
        return True
    return name.startswith(pfx)


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
