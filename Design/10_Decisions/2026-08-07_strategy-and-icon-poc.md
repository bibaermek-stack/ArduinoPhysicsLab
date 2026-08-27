# 2026-08-07 — Fluent 2 modernization strategy + icon PoC

## Decision

**Strategy B approved**: keep the existing architecture (Router, MainWindow, Sidebar, ThemeManager,
experiment pages, measurement pipeline) unchanged; selectively adopt Fluent visual language through
(1) vendored MIT-licensed Fluent System Icons and (2) the existing pyqtgraph dependency, without
adopting any Fluent *widget* framework.

**Rejected for this project** (see chat-delivered research report for full evidence):
- `PyQt-Fluent-Widgets` / `PySide6-Fluent-Widgets` (zhiyiYo) — GPLv3 (commercial license required to avoid
  copyleft), replaces Qt widget base classes (would break hundreds of tests that assert on exact widget
  types/private attributes), zero CI evidence for Python 3.14.
- `qt-material` — stale since 2024-05-16, would compete with ThemeManager for global stylesheet ownership.
- `Qt-Advanced-Docking-System` / `PyQtAds` — solves a docking problem this app doesn't have; Python binding
  wheels last published 2022 (cp36-abi3), no evidence of PySide6 6.11 / Python 3.14 compatibility.
- `PyQtDarkTheme` — hard-incompatible: `requires_python: >=3.7,<3.12` excludes this project's Python 3.14.
- `qtawesome`, `qtsass` — not rejected outright, but deliberately deferred: the first icon PoC uses vendored
  static SVGs only, to evaluate the lowest-risk option before adding any new runtime dependency.

## Frozen for this phase (per explicit instruction)

MainWindow, Router, Sidebar, experiment pages, measurement workspace, graph layout, DeviceManager,
repositories, database, navigation, ThemeManager production behavior, `requirements.txt`. No package
installed. `pyqtgraph` stays at the currently-installed 0.13.7 (no upgrade this phase).

## This phase's concrete output

- `Design/` reference folder structure created (this tree).
- 26 Fluent System Icon SVGs vendored under `Design/02_FluentIcons/svg/` (20 requested categories +
  6 Filled twins for the selected-state demo) — see `Design/02_FluentIcons/SOURCE.md` for exact mapping,
  source commit, and the one substitution (Circuit/schematic → Developer Board, flagged, not invented).
- License/notice preserved verbatim in `Design/09_Licenses/`.
- One isolated icon prototype (see prototype's own module docstring for architecture) — not imported by
  `app.py`, `MainWindow`, or `Router`.

## Next-phase question (not decided here)

Whether/how to integrate specific vendored icons into the real sidebar/toolbar in a future, separately
approved phase. Not in scope for this PoC.
