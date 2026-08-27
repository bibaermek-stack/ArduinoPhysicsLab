# Arduino Physics Lab — PyInstaller onedir спецификациясы (Phase 9,
# Production Deployment & Release Readiness, Part A "Windows Desktop
# Packaging").
#
# Onedir таңдалды, onefile ЕМЕС (§ Phase 9 Architecture Decision #1):
# onefile әр іске қосылымда уақытша қалтаға өзін-өзі ашады (баяу
# бастапқы жүктелу, PySide6/pyqtgraph көп Qt plugin-мен нашар
# үйлеседі), антивирус эвристикасын жиірек тудырады (бір "белгісіз"
# exe өзін-өзі runtime-да ашуы классикалық маркер), болашақ
# incremental жаңартуды қиындатады. Onedir мектеп IT қызметкеріне
# инспекциялауға/allowlist-ке қосуға ыңғайлырақ.
#
# ``Design/02_FluentIcons/svg/`` мен ``ui/resources/images/`` ғана
# ``core/resource_paths.py::resource_path()`` арқылы runtime-да
# нақты оқылады (§ audit) — ``Design/``-тің басқа ішкі қалталары
# (дизайн шешімдер құжаттамасы, лицензиялар, т.б.) runtime-ге ЕШБІР
# қатысы жоқ, сондықтан bundle-ге ЕНГІЗІЛМЕЙДІ (§ "keep the packaged
# app lean").

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

_PROJECT_ROOT = Path(SPECPATH).resolve().parent

_DATAS = [
    (str(_PROJECT_ROOT / "Design" / "02_FluentIcons" / "svg"), "Design/02_FluentIcons/svg"),
    (str(_PROJECT_ROOT / "ui" / "resources" / "images"), "ui/resources/images"),
    (str(_PROJECT_ROOT / "deployment.example.json"), "."),
]
_DATAS += collect_data_files("certifi")

# § "runtime does not depend on Python being installed system-wide" —
# ``PySide6.QtSerialPort`` (Arduino/COM порт байланысы) мен
# ``pyqtgraph`` PyInstaller-дың автоматты импорт анализінен өтпеуі
# мүмкін (динамикалық plugin/backend жүктеу), сондықтан ЕСКЕРТУ
# ретінде анық көрсетіледі.
_HIDDEN_IMPORTS = [
    "PySide6.QtSerialPort",
    "pyqtgraph",
    "pyqtgraph.graphicsItems",
    "pyqtgraph.exporters",
    "httpx",
    "httpcore",
    "certifi",
    "h11",
    "anyio",
    "idna",
    "core.deployment_config",
]
_HIDDEN_IMPORTS += collect_submodules("httpx")

a = Analysis(
    [str(_PROJECT_ROOT / "main.py")],
    pathex=[str(_PROJECT_ROOT)],
    binaries=[],
    datas=_DATAS,
    hiddenimports=_HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "py",
        "matplotlib",
        "scipy",
        "numba",
        "llvmlite",
        "IPython",
        "tkinter",
        "notebook",
        "sphinx",
        "tests",
        "server.tests",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# § "windowed (no console) — never expose Python tracebacks to ordinary
# students" (Part I) — ``sys.excepthook`` (main.py) ӘЛДЕҚАШАН толық
# traceback-ті rotating файл логына жазады, консоль терезесі қажет
# емес.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ArduinoPhysicsLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ArduinoPhysicsLab",
)
