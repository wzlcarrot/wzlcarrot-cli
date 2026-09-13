# PyInstaller spec for a single-file wzlcarrot binary.
# Build from the repo root:  uv run --extra binary pyinstaller packaging/pyinstaller/wzlcarrot.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = (
    collect_data_files("textual")
    + collect_data_files("rich")
    + collect_data_files("markdown_it")
)
hiddenimports = collect_submodules("textual")

a = Analysis(
    ["wzlcarrot_cli/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="wzlcarrot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
