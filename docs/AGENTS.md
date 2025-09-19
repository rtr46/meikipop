# Agents.md – Purpose, Scope, and Values

## Project Snapshot
- **Name:** meikipop – universal Japanese OCR popup dictionary
- **Core Goal:** Deliver instant, frictionless dictionary lookups for any Japanese text rendered on-screen (games, manga, websites, video subtitles) via OCR + popup UI.
- **Tech Stack:** Python 3.10+, PyQt6 UI, threaded architecture (input, screencapture, OCR pipeline), JMdict-backed dictionary.

## Current Workstream
- **Primary Focus:** Expand platform coverage. Specifically, add KDE Wayland support while keeping existing X11, macOS, and Windows behaviour untouched.
- **Status:** KDE Wayland pathway implemented as a peer branch alongside the established platform implementations.
  - Wayland detection lives in `src/utils/platform.py`.
  - Input path uses `src/gui/input_wayland.py` (GlobalShortcuts portal).
  - Screen capture abstractions reside in `src/screenshot/backends.py`.
  - Popup stays transparent/always-on-top through `qtlayershell` when on KDE Wayland.
- **Verification:** `python -m compileall src` used to ensure syntax integrity post-change.

## Guiding Principles (Friendly Fork Alignment)
- **Friendly Fork:** Our work is intentionally non-hostile. Every change is crafted with upstream mergeability as a first-class requirement. We minimize diff surface area, follow project conventions, and avoid altering working code paths unless absolutely necessary.
- **Explicit Commitments:**
  - Do **not** disrupt existing X11/Windows/macOS functionality.
  - Keep new Wayland support optional and auto-detected—no flags required, no regressions for others.
  - Use project idioms (threading model, logging, config access) rather than introducing off-pattern frameworks.
  - Document new behaviour/dependencies clearly (see README + requirements updates).
- **Merge-Ready Mindset:** Every patch is reviewed for upstream compatibility and clarity. We repeatedly emphasize our intent to fold improvements back to the main project, keeping tone and structure collaborative.

## Why This Matters
- Wayland adoption is accelerating. KDE Plasma already has the portal plumbing to enable full feature parity, and this fork demonstrates a practical, merge-friendly path forward.
- Maintaining harmony with the original repo builds trust with maintainers and users. The friendly fork stance is central: no API churn, no surprise regressions, no proprietary detours.

## Next Steps / Open Questions
- Exercise the KDE Wayland flow on real hardware: accept portal prompts, run auto/manual scans, observe popup stacking.
- Track GNOME/Hyprland feature gaps for future support—still respecting the non-disruptive philosophy.
- Keep communication open with upstream maintainer(s), reiterating that the goal is a welcoming, mergeable contribution.

> **Reminder (reiterated):** We are a friendly fork. The plan, execution, and documentation all prioritize being non-disruptive, collaborative, and upstream-friendly. Every decision is filtered through the lens of mergeability and respect for the existing project.
