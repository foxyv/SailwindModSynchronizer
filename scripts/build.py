"""Build a Windows executable and a desktop shortcut.

Usage (from the repo root, with the project venv active):

    python scripts/build.py
    python scripts/build.py --release
    python scripts/build.py --skip-shortcut
    python scripts/build.py --console
    python scripts/build.py --release --skip-sign

Default is a full PyInstaller freeze (parallel COLLECT, cache reused, no zip).
Pass --release for a clean freeze, Azure Authenticode signing, and a versioned zip.
Use --skip-sign for an unsigned zip.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS = REPO_ROOT / "assets"
PNG_ICON = ASSETS / "icon.png"
ICO_ICON = ASSETS / "icon.ico"
EXE_NAME = "SailwindModSynchronizer"
SHORTCUT_NAME = "Sailwind Mod Synchronizer.lnk"
DIST_DIR = REPO_ROOT / "dist" / EXE_NAME
FREEZE_ENTRY = Path(__file__).resolve().parent / "freeze_entry.py"
SIGN_EXTENSIONS = {".exe", ".dll", ".pyd"}
SIGN_BATCH = 16
COLLECT_SKIP_PARTS = (
    "qt6qml",
    "qt6quick",
    "qt6pdf",
    "qt6virtualkeyboard",
    "qtvirtualkeyboard",
    "translations",
)
MIN_SIGNTOOL_VERSION = (10, 0, 22621)
UNSUPPORTED_SIGNTOOL_VERSIONS = {(10, 0, 20348)}
TIMESTAMP_URL = "http://timestamp.acs.microsoft.com"

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

HIDDEN_IMPORTS = [
    "sailwind_mod_sync.app",
    "logging.handlers",
    "ctypes.wintypes",
    "html",
    "gzip",
    "zipfile",
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
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Sign freeze output with Azure Artifact Signing (implied by --release).",
    )
    parser.add_argument(
        "--skip-sign",
        action="store_true",
        help="Do not Authenticode-sign the freeze output.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Ignored; every freeze is a full PyInstaller build.",
    )
    args = parser.parse_args(argv)
    if args.sign and args.skip_sign:
        parser.error("use only one of --sign and --skip-sign")
    if args.release and not args.skip_sign:
        args.sign = True
    return args


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
    _copy_icons()
    if args.release:
        print("Release freeze (clean PyInstaller cache).")
    else:
        print("Full freeze (PyInstaller, parallel collect, no GitHub zip).")

    exe = DIST_DIR / f"{EXE_NAME}.exe"
    if not exe.is_file():
        raise SystemExit(f"PyInstaller did not produce {exe}")

    print(f"Built {exe}")

    if args.sign:
        sign_dist(DIST_DIR, exe)

    if args.release:
        version = _app_version()
        archive = zip_dist(DIST_DIR, REPO_ROOT / "dist" / f"{EXE_NAME}-{version}-windows.zip")
        print(f"Release zip {archive}")
        print("Upload that zip to a GitHub release so the app can auto-update.")

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


def _copy_icons() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ICO_ICON, DIST_DIR / "icon.ico")
    assets = DIST_DIR / "_internal" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ICO_ICON, assets / "icon.ico")
    shutil.copy2(PNG_ICON, assets / "icon.png")


def skip_collect_path(dest_name: str) -> bool:
    normalized = dest_name.replace("\\", "/").lower()
    parts = tuple(normalized.split("/"))
    if "translations" in parts:
        return True
    blob = "/".join(parts)
    return any(token in blob for token in COLLECT_SKIP_PARTS if token != "translations")


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


def default_signing_metadata_path() -> Path:
    override = os.environ.get("SMS_SIGNING_METADATA", "").strip()
    if override:
        return Path(override).expanduser()
    profile = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(profile) / "sms-signing" / "metadata.json"


def load_signing_metadata(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(
            "Azure Artifact Signing metadata not found.\n"
            f"  Expected: {path}\n"
            "Create that JSON file (see scripts/signing.metadata.example.json), or set "
            "SMS_SIGNING_METADATA, or pass --skip-sign for an unsigned zip."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid signing metadata JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Signing metadata must be a JSON object: {path}")
    required = ("Endpoint", "CodeSigningAccountName", "CertificateProfileName")
    missing = [key for key in required if not str(data.get(key) or "").strip()]
    if missing:
        raise SystemExit(f"Signing metadata at {path} is missing: {', '.join(missing)}")
    return data


def kit_version_tuple(folder_name: str) -> tuple[int, int, int] | None:
    parts = folder_name.split(".")
    if len(parts) < 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def find_signtool() -> Path:
    override = os.environ.get("SMS_SIGNTOOL", "").strip()
    if override:
        path = Path(override)
        if not path.is_file():
            raise SystemExit(f"SMS_SIGNTOOL is set but not a file: {path}")
        return path
    kits = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin"
    found: list[tuple[tuple[int, int, int], Path]] = []
    if kits.is_dir():
        for child in kits.iterdir():
            version = kit_version_tuple(child.name)
            if version is None:
                continue
            if version in UNSUPPORTED_SIGNTOOL_VERSIONS or version < MIN_SIGNTOOL_VERSION:
                continue
            candidate = child / "x64" / "signtool.exe"
            if candidate.is_file():
                found.append((version, candidate))
    if found:
        found.sort()
        return found[-1][1]
    which = shutil.which("signtool")
    if which:
        return Path(which)
    raise SystemExit(
        "signtool.exe not found. Install the Windows SDK (10.0.22621 or later, not 10.0.20348) "
        "or Artifact Signing Client Tools, or set SMS_SIGNTOOL."
    )


def _dlib_search_roots() -> list[Path]:
    roots: list[Path] = []
    override = os.environ.get("SMS_SIGNING_DLIB", "").strip()
    if override:
        roots.append(Path(override))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    roots.extend(
        [
            program_files / "Microsoft Artifact Signing Client Tools",
            program_files / "Azure Artifact Signing Client Tools",
            program_files / "Microsoft Azure Artifact Signing Client Tools",
            program_files_x86 / "Microsoft Artifact Signing Client Tools",
            local_app / "Microsoft" / "MicrosoftArtifactSigningClientTools",
            Path.home() / ".nuget" / "packages" / "microsoft.artifactsigning.client",
            Path.home() / ".nuget" / "packages" / "microsoft.trusted.signing.client",
            local_app / "Microsoft" / "WinGet" / "Packages",
        ]
    )
    return roots


def find_signing_dlib() -> Path:
    override = os.environ.get("SMS_SIGNING_DLIB", "").strip()
    if override:
        path = Path(override)
        if path.is_file():
            return path
        nested = path / "x64" / "Azure.CodeSigning.Dlib.dll"
        if nested.is_file():
            return nested
        nested = path / "Azure.CodeSigning.Dlib.dll"
        if nested.is_file():
            return nested
    for root in _dlib_search_roots():
        if not root.exists():
            continue
        if root.is_file() and root.name.lower() == "azure.codesigning.dlib.dll":
            return root
        for relative in (
            Path("Azure.CodeSigning.Dlib.dll"),
            Path("bin") / "x64" / "Azure.CodeSigning.Dlib.dll",
            Path("x64") / "Azure.CodeSigning.Dlib.dll",
        ):
            direct = root / relative
            if direct.is_file():
                return direct
        if root.is_dir():
            children = [root]
            if root.name.lower() == "packages" and "winget" in str(root).lower():
                children = [
                    child
                    for child in root.iterdir()
                    if child.is_dir()
                    and ("artifactsigning" in child.name.lower() or "trusted.signing" in child.name.lower())
                ]
            for child in children:
                matches = sorted(
                    path
                    for path in child.rglob("Azure.CodeSigning.Dlib.dll")
                    if path.name.lower() == "azure.codesigning.dlib.dll"
                )
                if matches:
                    return matches[-1]
    raise SystemExit(
        "Azure.CodeSigning.Dlib.dll not found. Install with:\n"
        "  winget install -e --id Microsoft.Azure.ArtifactSigningClientTools\n"
        "or set SMS_SIGNING_DLIB to the x64 dlib path."
    )


def binaries_to_sign(dist_dir: Path) -> list[Path]:
    files = [
        path
        for path in sorted(dist_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in SIGN_EXTENSIONS
    ]
    if not files:
        raise SystemExit(f"No .exe/.dll/.pyd files to sign in {dist_dir}")
    return files


def sign_files(signtool: Path, dlib: Path, metadata: Path, files: list[Path]) -> None:
    for index in range(0, len(files), SIGN_BATCH):
        batch = files[index : index + SIGN_BATCH]
        cmd = [
            str(signtool),
            "sign",
            "/fd",
            "SHA256",
            "/tr",
            TIMESTAMP_URL,
            "/td",
            "SHA256",
            "/dlib",
            str(dlib),
            "/dmdf",
            str(metadata),
            *[str(path) for path in batch],
        ]
        print(f"Signing {len(batch)} file(s) ({index + 1}-{index + len(batch)} of {len(files)})…")
        subprocess.check_call(cmd)


def sign_dist(dist_dir: Path, exe: Path) -> None:
    if os.name != "nt":
        raise SystemExit("Authenticode signing is only supported on Windows.")
    metadata = default_signing_metadata_path()
    load_signing_metadata(metadata)
    signtool = find_signtool()
    dlib = find_signing_dlib()
    files = binaries_to_sign(dist_dir)
    print(f"Signing {len(files)} binaries with Azure Artifact Signing")
    print(f"  metadata: {metadata}")
    print(f"  signtool: {signtool}")
    print(f"  dlib:     {dlib}")
    print("If a browser or az login prompt appears, finish it with the account that has")
    print("the Artifact Signing Certificate Profile Signer role.")
    try:
        sign_files(signtool, dlib, metadata, files)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"signtool failed with exit code {exc.returncode}.\n"
            "Check az login, the Certificate Profile Signer role, and that Endpoint "
            "in metadata.json matches the Artifact Signing account region."
        ) from exc
    if not exe.is_file():
        raise SystemExit(f"Signed exe missing: {exe}")
    print(f"Signed {exe}")


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
            "--collect-data",
            "certifi",
            "--add-data",
            f"{ICO_ICON}{add_data_sep}assets",
            "--add-data",
            f"{PNG_ICON}{add_data_sep}assets",
            str(FREEZE_ENTRY),
        ]
    )
    for module in HIDDEN_IMPORTS:
        args.extend(["--hidden-import", module])
    for module in QT_EXCLUDES:
        args.extend(["--exclude-module", module])
    return args


def _run_pyinstaller(*, windowed: bool, clean: bool) -> None:
    import PyInstaller.__main__

    _patch_collect()
    PyInstaller.__main__.run(pyinstaller_args(windowed=windowed, clean=clean))


def _patch_collect() -> None:
    from PyInstaller.building.api import COLLECT
    from PyInstaller.building.utils import _make_clean_directory, process_collected_binary
    from PyInstaller.compat import is_win

    def assemble(self) -> None:  # type: ignore[no-untyped-def]
        _make_clean_directory(self.name)
        print("Building COLLECT with parallel copy…")
        jobs: list[tuple[str, str, str]] = []
        skipped = 0
        for dest_name, src_name, typecode in self.toc:
            if typecode not in {"DEPENDENCY", "SYMLINK"} and not os.path.exists(src_name):
                continue
            if os.pardir in os.path.normpath(dest_name).split(os.sep) or os.path.isabs(dest_name):
                raise SystemExit(f"ERROR: attempting to store file outside of the dist directory: {dest_name!r}.")
            if skip_collect_path(dest_name):
                skipped += 1
                continue
            if typecode in ("EXECUTABLE", "PKG"):
                dest_path = os.path.join(self.name, dest_name)
            else:
                dest_path = os.path.join(self.name, self.contents_directory or "", dest_name)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if typecode in ("EXTENSION", "BINARY"):
                src_name = process_collected_binary(
                    src_name,
                    dest_name,
                    use_strip=self.strip_binaries,
                    use_upx=self.upx_binaries,
                    upx_exclude=self.upx_exclude,
                    target_arch=self.target_arch,
                    codesign_identity=self.codesign_identity,
                    entitlements_file=self.entitlements_file,
                    strict_arch_validation=(typecode == "EXTENSION"),
                )
            jobs.append((src_name, dest_path, typecode))

        def copy_job(job: tuple[str, str, str]) -> None:
            src_name, dest_path, typecode = job
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if typecode == "SYMLINK":
                if is_win and os.path.sep == "/":
                    src_name = src_name.replace(os.path.sep, "\\")
                if os.path.lexists(dest_path):
                    os.unlink(dest_path)
                os.symlink(src_name, dest_path)
                return
            if typecode == "DEPENDENCY":
                return
            shutil.copyfile(src_name, dest_path)
            if typecode in ("EXTENSION", "BINARY", "EXECUTABLE") or (
                typecode == "DATA" and os.access(src_name, os.X_OK)
            ):
                os.chmod(dest_path, 0o755)

        workers = max(4, min(32, (os.cpu_count() or 4) * 2))
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(copy_job, jobs))
        elapsed = time.perf_counter() - started
        print(
            f"COLLECT copied {len(jobs)} file(s) with {workers} workers in {elapsed:.1f}s "
            f"({skipped} skipped)."
        )

    COLLECT.assemble = assemble  # type: ignore[method-assign]


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
