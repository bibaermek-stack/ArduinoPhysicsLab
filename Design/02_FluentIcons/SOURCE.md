# Fluent System Icons — vendored subset

**Source repository:** https://github.com/microsoft/fluentui-system-icons
**Vendored from commit:** `9e9a1766ae48f4a138fed896b25a59a5f6619230` (`main`, 2026-08-04)
**License:** MIT (see [`../09_Licenses/fluentui-system-icons_LICENSE.txt`](../09_Licenses/fluentui-system-icons_LICENSE.txt) and
[`../09_Licenses/fluentui-system-icons_NOTICE.txt`](../09_Licenses/fluentui-system-icons_NOTICE.txt), both copied verbatim from the
source repository root).

These are **static SVG assets only** — no package was installed, no code was copied. Each file below was fetched directly from
`raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/<Icon Name>/SVG/<file>.svg`.

## Icons selected (20 categories requested)

| # | Category (requested) | Fluent icon name | File |
|---|---|---|---|
| 1 | Home | Home | `ic_fluent_home_24_regular.svg` |
| 2 | Laboratory / experiment | Beaker | `ic_fluent_beaker_24_regular.svg` |
| 3 | Devices / plug | Plug Connected | `ic_fluent_plug_connected_24_regular.svg` |
| 4 | Results / data | Clipboard Data Bar | `ic_fluent_clipboard_data_bar_24_regular.svg` |
| 5 | Graphs | Chart Multiple | `ic_fluent_chart_multiple_24_regular.svg` |
| 6 | Calculations | Calculator | `ic_fluent_calculator_24_regular.svg` |
| 7 | Instructions / book | Book | `ic_fluent_book_24_regular.svg` |
| 8 | Circuit / schematic | Developer Board *(closest available match — see note below)* | `ic_fluent_developer_board_24_regular.svg` |
| 9 | Export | Arrow Export | `ic_fluent_arrow_export_24_regular.svg` |
| 10 | Settings | Settings | `ic_fluent_settings_24_regular.svg` |
| 11 | Help | Question Circle | `ic_fluent_question_circle_24_regular.svg` |
| 12 | Student / user | Person | `ic_fluent_person_24_regular.svg` |
| 13 | Theme / mode | Dark Theme | `ic_fluent_dark_theme_24_regular.svg` |
| 14 | Back navigation | Arrow Left | `ic_fluent_arrow_left_24_regular.svg` |
| 15 | Start / play | Play | `ic_fluent_play_24_regular.svg` |
| 16 | Stop | Stop | `ic_fluent_stop_24_regular.svg` |
| 17 | Delete / clear | Delete | `ic_fluent_delete_24_regular.svg` |
| 18 | Zoom | Zoom In | `ic_fluent_zoom_in_24_regular.svg` |
| 19 | Reset | Arrow Reset | `ic_fluent_arrow_reset_24_regular.svg` |
| 20 | Fullscreen | Full Screen Maximize | `ic_fluent_full_screen_maximize_24_regular.svg` |

**Note on #8 (Circuit / schematic):** the Fluent System Icons set has no icon literally named "Circuit" or "Schematic". Searched
the full regular-icon index (`Cpu`, `Chip`, `Circuit`, `Electrical`, `Resistor`, `Board`, `Developer Board`) — only "Board" and
"Developer Board" exist, and "Developer Board" (a PCB-style glyph) is the closest visual match to an electronics circuit. Per the
instruction not to invent replacements, this is flagged explicitly as a substitution rather than a literal match, for your review
during integration — not silently presented as "Circuit."

## Filled variants (added for the "selected" state demo only)

The prototype needs to demonstrate a selected/active state on sidebar-style nav buttons. Fluent's own convention for that is
swapping the Regular glyph for its Filled counterpart (not just a background highlight), so these 6 Filled twins were vendored
alongside their Regular counterparts:

| Icon | File |
|---|---|
| Home | `ic_fluent_home_24_filled.svg` |
| Beaker | `ic_fluent_beaker_24_filled.svg` |
| Person | `ic_fluent_person_24_filled.svg` |
| Settings | `ic_fluent_settings_24_filled.svg` |
| Play | `ic_fluent_play_24_filled.svg` |
| Stop | `ic_fluent_stop_24_filled.svg` |

**Subtotal after Phases 6-7: 26 SVGs.**

## Phase 8 — Gap closure candidates (research + vendoring only, NOT yet integrated)

**Vendored from commit:** `9e9a1766ae48f4a138fed896b25a59a5f6619230` (`main`, 2026-08-04) — **same commit as above**, confirmed
unchanged via the GitHub API immediately before this vendoring pass (repo `main` HEAD was still `9e9a1766a...` at fetch time).
No license/NOTICE diff to report — `../09_Licenses/` files remain valid and untouched.

These SVGs close previously-identified icon gaps from Phases 6-7 (Sidebar `feedback_student`/`feedback_teacher`/`data_log`,
Sidebar `switch_role_button`, Sidebar `device_summary_label`, and graph-toolbar `_pan_mode_button`/`_region_button`/
`_delta_button`/`_copy_summary_button`). **Vendored for comparison only — no production code references these files yet.**
Each row's "Reason selected" explains why it qualifies as a strong (not forced) semantic match; the primary recommendation
per control is marked **(recommended)**.

| # | Control | Purpose | Fluent icon name | File | Reason selected |
|---|---|---|---|---|---|
| 21 | feedback_student / feedback_teacher | Feedback/comment | Comment **(recommended)** | `ic_fluent_comment_24_regular.svg` | Simplest, most universally recognized speech-bubble "feedback" glyph; doesn't duplicate any icon already visible elsewhere in Sidebar. |
| 22 | feedback_student / feedback_teacher (selected state) | Feedback/comment, filled | Comment | `ic_fluent_comment_24_filled.svg` | Filled twin — these are Sidebar nav items, so if integrated they'd follow the existing Regular→Filled `:checked` convention (see Phase 6). |
| 23 | feedback_student / feedback_teacher (alternate) | Feedback/comment | Chat | `ic_fluent_chat_24_regular.svg` | Close second — a speech bubble with content lines, arguably reads more "message/conversation" than plain "comment." Vendored so you can compare both directly rather than take my word for it. |
| 24 | data_log | Data journal/log | Notebook **(recommended)** | `ic_fluent_notebook_24_regular.svg` | "Notebook" maps directly to "журнал" (journal); visually distinct from the already-used Clipboard Data Bar (Results), avoiding an in-panel duplicate. |
| 25 | data_log (selected state) | Data journal/log, filled | Notebook | `ic_fluent_notebook_24_filled.svg` | Filled twin, same Sidebar `:checked` rationale as #22. |
| 26 | switch_role_button | Role/mode switch | People Swap **(recommended)** | `ic_fluent_people_swap_24_regular.svg` | Two person glyphs with a swap arrow — the single best semantic match found in this entire research pass, since the action is specifically swapping between two *people/roles* (Teacher ↔ Student), not generic content. |
| 27 | switch_role_button (selected/future) | Role/mode switch, filled | People Swap | `ic_fluent_people_swap_24_filled.svg` | Filled twin, vendored in case a future phase wants it; `switch_role_button` isn't currently checkable so this isn't immediately used. |
| 28 | switch_role_button (alternate) | Role/mode switch | Arrow Swap | `ic_fluent_arrow_swap_24_regular.svg` | Generic two-opposite-arrows "swap" glyph — simpler, less role-specific, still a strong match. |
| 29 | device_summary_label (future candidate — label itself NOT modified) | Connected device | USB Plug | `ic_fluent_usb_plug_24_regular.svg` | Distinct from the already-vendored Plug Connected (used for Sidebar's "Devices" nav item) — offered so a future integration can avoid a third reuse of the same glyph. Plug Connected itself remains a valid, already-vendored option too. |
| 30 | _pan_mode_button | Pan/drag graph view | Hand Left **(recommended)** | `ic_fluent_hand_left_24_regular.svg` | Most literal match to the current ✋ emoji; universally recognized "grab/pan" metaphor (matches Google Maps/Figma-style hand tool). |
| 31 | _pan_mode_button (alternate) | Pan/drag graph view | Drag | `ic_fluent_drag_24_regular.svg` | Four-way-arrow-around-a-dot glyph — the precise UX convention several charting/mapping tools use specifically for a "pan" tool (distinct from a general grab cursor). |
| 32 | _region_button | Interval/region selection | Select Object **(recommended, imperfect)** | `ic_fluent_select_object_24_regular.svg` | Dashed rectangle with corner handles — a reasonable "select a bounded area for analysis" glyph, but **not a perfect match**: no vendored icon precisely conveys "select a horizontal interval on a time axis." Flagged honestly below rather than force-rated higher. |
| 33 | _delta_button | A/B delta measurement | Arrow Between Down **(recommended)** | `ic_fluent_arrow_between_down_24_regular.svg` | Two arrows pointing toward each other — reads as "the gap/distance between two points," close to the literal meaning of a Δ (A↔B) measurement. |
| 34 | _delta_button (alternate) | A/B delta measurement | Arrows Bidirectional | `ic_fluent_arrows_bidirectional_24_regular.svg` | Bold double-headed arrow — a cleaner render of the *existing* "↔" glyph concept; more generic "back-and-forth" than "distance between two specific points." |
| 35 | _copy_summary_button | Copy result to clipboard | Copy **(recommended)** | `ic_fluent_copy_24_regular.svg` | The universal two-overlapping-rectangles "copy/duplicate" glyph used across virtually every OS/app — a clean, honest, unambiguous match (unlike Clipboard Data Bar, rejected in Phase 7 for reading as "report," not "copy"). |

**Considered but NOT vendored** (below the "strong match" bar, or redundant with a vendored candidate):
- **History** (`Data Journal/Log`, 7/10) — reads as "past events over time" more than "journal object"; Notebook scored higher and was vendored instead.
- **Clipboard Task List** (`Data Journal/Log`, 6/10, only ships at 16px) — checklist-flavored, weaker fit than Notebook.
- **Hand Right** — mirror image of the vendored Hand Left; no semantic difference, redundant to vendor both.
- **Crop** (`Region/range select`, 5/10) — crop-marks glyph implies trimming/removing, weaker fit than Select Object for an analysis-interval tool.

**Marked unresolved:** none outright rejected as "no honest icon exists" this round — every gap had at least one defensible candidate — but **#32 (region_button)** and, to a lesser extent, **#33/#34 (delta_button)** are honestly imperfect matches, not confident ones; treat them as "best available" rather than "found the right icon," and feel free to reject them at integration time.

**Files added this phase: 15 SVGs** (10 Regular + 5 Filled). **Running total: 41 SVGs** in `Design/02_FluentIcons/svg/`.
