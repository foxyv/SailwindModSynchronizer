from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from sailwind_mod_sync.config import AppConfig
from sailwind_mod_sync.manager import Manager
from sailwind_mod_sync.paths import AppPaths
from sailwind_mod_sync.ui.main_window import MainWindow


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="sms-smoke-"))
    os.environ["SAILWIND_MOD_SYNC_HOME"] = str(root)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    manager = Manager(paths=AppPaths(root), config=AppConfig())
    print("data root", root)
    print("catalog refresh")
    entries = manager.refresh_catalog()
    print(f"catalog entries: {len(entries)}")
    gamma = next(entry for entry in entries if entry.primary_guid == "com.dizzy.sailwind.gamma")
    pack = manager.packs.list_packs()[0]
    print("install BepInEx and Dizzy.Gamma")
    manager.prepare_pack(pack.id)
    pinned = manager.install_mod(
        pack.id,
        gamma.primary_guid,
        repo=gamma.repo,
        version=gamma.latest_version,
        version_raw=gamma.latest_raw,
    )
    print(f"installed {pinned.guid} {pinned.version} folders={pinned.plugin_folders}")
    export_path = root / "dizzy.json"
    manager.export_pack(pack.id, export_path, bundle=False)
    print(f"exported {export_path} bytes={export_path.stat().st_size}")
    window = MainWindow(manager)
    window.show()
    print("ui", window.windowTitle(), "packs", window.pack_list.count())
    manager.close()
    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
