# 2026-08-28 — Laboratory teal brand identity

## Decision

Unify the public website and the Windows desktop accent around the existing
laboratory token `#00897B` (`COLOR_SECTION_LABORATORY` / website `--lab`).

Microsoft Fluent blue (`#0078D4` / `#2563EB`) stays only as a *section*
color for electromagnetism and as one classroom accent — not as the product
primary.

## Why

The website already spoke "физика зертханасы" in teal. The desktop still
looked like a generic Windows 11 admin tool. One accent makes the .exe and
the cloud site feel like the same product.

## Changed

- `ui/themes/theme_palettes.py` dark + light `COLOR_ACCENT*` / selected / focus
- `ui/themes/theme_manager.py` matching default tokens
- Public site focus rings, hero live-readout, stats strip
- Cache-bust `/static/app.css?v=4`

## Frozen

Layout geometry, button height, sidebar width, object names, Router,
experiment workspace structure, and background tokens used by tests
(`#1C1C1E`, `#EEF1F6`) are unchanged.
