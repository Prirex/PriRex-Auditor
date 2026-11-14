# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-спецификация для «PriRex Auditor».

Сборка:  python -m PyInstaller "PriRex Auditor.spec" --noconfirm
Итог:    dist/PriRex Auditor.exe  (--onefile, --windowed)
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)
ASSETS = ROOT / "assets"

# --- данные приложения: QSS-тема, логотип, иконки ---------------------------
datas = [
    (str(ASSETS), "assets"),
]
if (ROOT / "version.json").exists():
    datas.append((str(ROOT / "version.json"), "."))

hiddenimports = [
    "bs4",
    "lxml",
    "lxml.etree",
    "lxml.html",
    "httpx",
    "httpcore",
    "h11",
    "anyio",
    "anyio._backends._asyncio",
    "sniffio",
    "certifi",
    "idna",
    "loguru",
    "pydantic",
    "pydantic_core",
    "reportlab",
    "reportlab.pdfbase._fontdata",
    "reportlab.platypus",
    "PIL",
    "PIL._tkinter_finder",
    "packaging",
    "app",
]

try:
    report_datas, report_binaries, report_hidden = collect_all("reportlab")
    datas += report_datas
    hiddenimports += report_hidden
except Exception:
    pass

# Playwright: python-пакет в бандл, браузер — системный Chrome/Edge,
# либо установленный `python -m playwright install chromium`.
try:
    pw_datas, pw_binaries, pw_hidden = collect_all("playwright")
    datas += pw_datas
    hiddenimports += pw_hidden
except Exception:
    pw_binaries = []

hiddenimports += collect_submodules("app")

excludes = [
    "tkinter",
    "sqlite3",
    "unittest",
    "pydoc_data",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtTest",
    "PySide6.QtNetworkAuth",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtSensors",
    "PySide6.QtPositioning",
    "PySide6.QtWebSockets",
    "PySide6.QtWebChannel",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=pw_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PriRex Auditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / "logo.ico"),
    version=str(ROOT / "tools" / "version_info.txt")
    if (ROOT / "tools" / "version_info.txt").exists()
    else None,
)
