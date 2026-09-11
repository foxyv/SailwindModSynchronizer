# Sailwind Mod Synchronizer

A Qt (PySide6) mod manager for [Sailwind](https://store.steampowered.com/app/1764530/Sailwind/). It catalogs mods from [ModVersionChecker](https://github.com/bryon82/SailwindModVersionChecker), caches versioned zips in a Maven-like local library, and launches isolated ModPacks through UnityDoorstop so the Steam game folder stays vanilla.

## Requirements

- Python 3.11+
- Windows (Sailwind / Doorstop `winhttp.dll`)
- A Sailwind install (Steam appid `1764530`)

## Install and run

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
sailwind-mod-sync
```

Or: `python -m sailwind_mod_sync`

## Data

Config, catalog cache, artifact library, and ModPack instances live under:

`%LOCALAPPDATA%\SailwindModSynchronizer`

Override with `SAILWIND_MOD_SYNC_HOME`.

BepInEx is downloaded from Thunderstore **BepInExPack**. Mods are downloaded from GitHub/GitLab **release zip assets** listed in ModVersionChecker. On the Catalog tab you can also **Add GitHub repo** for projects that are not in that list. Play copies `winhttp.dll` into the game folder and launches `Sailwind.exe` with `--doorstop-target-assembly` pointed at the selected pack.

## Tests

```powershell
pytest
```

## Windows executable

From the repo root, with the venv active:

```powershell
pip install -e ".[dev,build]"
.\scripts\build.ps1
```

Or: `python scripts/build.py`

That compiles `dist\SailwindModSynchronizer\SailwindModSynchronizer.exe`, embeds `assets/icon.png` as the application icon, and creates a **Sailwind Mod Synchronizer** shortcut on the Desktop. Pass `-SkipShortcut` / `--skip-shortcut` to skip the shortcut.
