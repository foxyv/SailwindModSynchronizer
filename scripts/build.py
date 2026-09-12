"""Build a Windows executable and a desktop shortcut.

Usage (from the repo root, with the project venv active):

    python scripts/build.py
    python scripts/build.py --release
    python scripts/build.py --skip-shortcut
    python scripts/build.py --console

Default is an incremental freeze: reuse the PyInstaller cache, skip UPX, and skip
the GitHub zip. Pass --release for a clean freeze and a versioned zip.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS = REPO_ROOT / "assets"
PNG_ICON = ASSETS / "icon.png"
ICO_ICON = ASSETS / "icon.ico"
EXE_NAME = "SailwindModSynchronizer"
SHORTCUT_NAME = "Sailwind Mod Synchronizer.lnk"
DIST_DIR = REPO_ROOT / "dist" / EXE_NAME

QT_EXCLUDES = [
    "tkinter",
    "unittest",
    "pydoc",
    "PIL",
    "PyInstaller",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile Sailwind Mod Synchronizer to an executable.")
    parser.add_argument(
        "--release",
        action="store_true",
        help="Clean freeze and write a versioned zip for a GitHub release.",
    )
    parser.add_argument("--skip-shortcut", action="store_true", help="Do not create a Desktop shortcut.")
    parser.add_argument("--console", action="store_true", help="Show a console window (useful for debugging).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    os.chdir(REPO_ROOT)
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir in sys.path:
        sys.path.remove(scripts_dir)
    if not PNG_ICON.is_file():
        raise SystemExit(f"Missing icon PNG: {PNG_ICON}")

    _ensure_build_deps()
    write_ico(PNG_ICON, ICO_ICON)
    _run_pyinstaller(windowed=not args.console, clean=args.release)

    exe = DIST_DIR / f"{EXE_NAME}.exe"
    if not exe.is_file():
        raise SystemExit(f"PyInstaller did not produce {exe}")

    shutil.copy2(ICO_ICON, DIST_DIR / "icon.ico")
    print(f"Built {exe}")

    if args.release:
        version = _app_version()
        archive = zip_dist(DIST_DIR, REPO_ROOT / "dist" / f"{EXE_NAME}-{version}-windows.zip")
        print(f"Release zip {archive}")
        print("Upload that zip to a GitHub release so the app can auto-update.")
    else:
        print("Incremental freeze (cache reused, no GitHub zip).")
        print("Use --release for a clean build and a versioned zip.")

    if not args.skip_shortcut:
        shortcut = create_desktop_shortcut(exe, DIST_DIR / "icon.ico")
        print(f"Desktop shortcut: {shortcut}")
    return 0


def _ensure_build_deps() -> None:
    try:
        import PIL  # noqa: F401
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0", "pillow>=10.0"]
        )


def write_ico(png_path: Path, ico_path: Path) -> Path:
    from PIL import Image

    image = Image.open(png_path).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(ico_path, format="ICO", sizes=sizes)
    return ico_path


def _app_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("version"):
            _, _, value = stripped.partition("=")
            return value.strip().strip('"').strip("'")
    return "0.0.0"


def zip_dist(source: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    with ZipFile(dest, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    return dest


def pyinstaller_args(*, windowed: bool, clean: bool) -> list[str]:
    add_data_sep = ";" if os.name == "nt" else ":"
    args = ["--noconfirm", "--noupx"]
    if clean:
        args.append("--clean")
    args.extend(
        [
            "--windowed" if windowed else "--console",
            "--name",
            EXE_NAME,
            "--icon",
            str(ICO_ICON),
            "--paths",
            str(REPO_ROOT / "src"),
            "--collect-submodules",
            "sailwind_mod_sync",
            "--add-data",
            f"{ICO_ICON}{add_data_sep}assets",
            "--add-data",
            f"{PNG_ICON}{add_data_sep}assets",
            str(REPO_ROOT / "src" / "sailwind_mod_sync" / "__main__.py"),
        ]
    )
    for module in QT_EXCLUDES:
        args.extend(["--exclude-module", module])
    return args


def _run_pyinstaller(*, windowed: bool, clean: bool) -> None:
    import PyInstaller.__main__

    PyInstaller.__main__.run(pyinstaller_args(windowed=windowed, clean=clean))


def desktop_dir() -> Path:
    home = Path.home()
    candidates = [
        Path(os.environ.get("USERPROFILE", str(home))) / "Desktop",
        home / "OneDrive" / "Desktop",
        home / "Desktop",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


def create_desktop_shortcut(exe: Path, icon: Path) -> Path:
    desktop = desktop_dir()
    desktop.mkdir(parents=True, exist_ok=True)
    shortcut = desktop / SHORTCUT_NAME
    exe = exe.resolve()
    icon = icon.resolve()
    working = str(exe.parent)
    ps = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut({_ps_quote(str(shortcut))})
$shortcut.TargetPath = {_ps_quote(str(exe))}
$shortcut.WorkingDirectory = {_ps_quote(working)}
$shortcut.WindowStyle = 1
$shortcut.Description = 'Sailwind Mod Synchronizer'
$shortcut.IconLocation = {_ps_quote(f'{icon},0')}
$shortcut.Save()
"""
    subprocess.check_call(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps]
    )
    if not shortcut.exists():
        raise SystemExit(f"Failed to create shortcut at {shortcut}")
    return shortcut


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
