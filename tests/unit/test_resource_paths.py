"""core/resource_paths.py юнит-тесттері (Phase 9 — Production
Deployment & Release Readiness, § Part C "Resource Path Abstraction").

Dev режимі мен PyInstaller frozen режимін (``sys.frozen``/``sys.
_MEIPASS``) ажырату НАҚТЫ дұрыс екенін тексереді — ешбір тест ``D:\\...``
сияқты дамытушы машинаға тән жолды болжамайды (§ "Do not write brittle
tests tied to the developer's D:\\ path").
"""

from pathlib import Path

from core.resource_paths import _project_root, resource_path


def test_dev_mode_resolves_to_repo_root() -> None:
    """§ dev режимде ``sys.frozen`` жоқ — жоба түбірі осы файлдың ӨЗ
    орналасуынан (бір деңгей жоғары) есептеледі, кез келген машинада."""
    root = _project_root()

    assert (root / "core" / "resource_paths.py").is_file()
    assert (root / "main.py").is_file()


def test_dev_mode_resource_path_joins_correctly() -> None:
    path = resource_path("Design", "02_FluentIcons", "svg")

    assert path == _project_root() / "Design" / "02_FluentIcons" / "svg"
    assert path.is_dir()


def test_frozen_mode_uses_meipass(monkeypatch) -> None:
    """§ PyInstaller bundle ішінде (onedir НЕМЕСЕ onefile — екеуінде де
    ``sys._MEIPASS`` орнатылады) ресурс жолы ЕШҚАШАН dev-режимдегі
    ``__file__``-ге қатысты есептелмейді."""
    import core.resource_paths as resource_paths_module

    monkeypatch.setattr(resource_paths_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        resource_paths_module.sys, "_MEIPASS", r"C:\fake\bundle\root", raising=False
    )

    path = resource_paths_module.resource_path("Design", "02_FluentIcons", "svg")

    assert path == Path(r"C:\fake\bundle\root") / "Design" / "02_FluentIcons" / "svg"


def test_frozen_mode_without_meipass_falls_back_to_executable_dir(monkeypatch) -> None:
    """§ қорғаныс жағдайы — теориялық түрде ``frozen`` ақиқат, БІРАҚ
    ``_MEIPASS`` жоқ болса (әдетте болмауы тиіс), exe-мен БІРДЕЙ
    қалтаға түседі, exception шықпайды."""
    import core.resource_paths as resource_paths_module

    monkeypatch.setattr(resource_paths_module.sys, "frozen", True, raising=False)
    monkeypatch.delattr(resource_paths_module.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(
        resource_paths_module.sys, "executable", r"C:\fake\install\ArduinoPhysicsLab.exe"
    )

    path = resource_paths_module.resource_path("Design")

    assert path == Path(r"C:\fake\install") / "Design"
