---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "workflow/tasks/glass_ui_polish.md"
---
# glass ui polish

> Managed mirror of `workflow/tasks/glass_ui_polish.md`. Edit the source file, not this copy.

# Task: Apple-style frosted-glass status pills + premium motion (white theme)

## Objective
Refine the Spencer dashboard chrome to a calm, premium, Apple-glass feel WHILE
STAYING ON A WHITE LAYOUT. Fix three reported problems and elevate the status
pills to real frosted-glass. Styling only — no data element, fetch, or honest
empty/label may be removed or changed. The manager reviews every line in-browser
before this lands.

## Files
- `frontend/src/index.css` (theme, animations, glass utilities)
- `frontend/src/App.jsx` Header status row (the Paper mode / Backend / Live
  trading pills, currently around the `border-t ... bg-[#fafbfc]` row).

## Problems to fix
1. **Choppy/slow scroll motion.** Ensure the scroll reveal is GPU-light and
   cannot make the page stutter: the section-rise reveal must be opacity +
   small translateY ONLY (no rotateX, no perspective, no scale, no filter on
   scroll). Cap transitions to transform/opacity. Confirm nothing sets a
   persistent `will-change` on many elements. Keep the existing
   `prefers-reduced-motion` opt-out.
2. **Text over the instrument panel not clearly visible.** Audit text placed on
   tinted/gradient/glass surfaces and guarantee at least WCAG AA contrast
   (≈4.5:1 for body, 3:1 for large/labels). Frosted glass must use a strong
   enough white tint that dark slate text (#0f172a / #1e293b) stays crisp — never
   light-gray text on a light glass tile.
3. **Glass shimmer too fast.** If any shimmer/sweep exists, slow it to a premium
   cadence (~6s, ease-in-out, low amplitude). Add at most one subtle, slow
   shimmer; do not add busy motion. It must pause under prefers-reduced-motion.

## Glass pill design (the headline ask)
Turn the header status pills into Apple-style frosted glass ON WHITE:
- Semi-transparent white fill (e.g. `rgba(255,255,255,0.6)`) with
  `backdrop-filter: blur(12px) saturate(140%)` (and `-webkit-` prefix).
- Hairline border `1px solid rgba(255,255,255,0.7)` plus a soft outer shadow
  `0 1px 2px rgba(15,23,42,0.06)` and a faint inset top highlight
  `inset 0 1px 0 rgba(255,255,255,0.8)` for real glass depth.
- Rounded-full, comfortable padding, a small status dot, crisp dark label text.
- Status SEMANTICS must remain exact and honest:
  * "Paper mode" (always)
  * Backend status dot+label: connected (emerald) / checking (amber) /
    disconnected handled by the existing red banner — do not invent a state.
  * Live/broker safety: keep it explicit. RESTORE the distinct broker line that
    was merged away — show BOTH "Live trading off" AND "Broker execution off"
    (two pills or one pill with both phrases). The safety posture must read
    unambiguously; this is doctrine, not decoration.
- Provide a reusable `.glass-pill` utility/class in index.css so the style is
  defined once, not repeated inline.

## Hard constraints
- Layout stays WHITE (#ffffff cards on the existing light canvas). No dark mode,
  no dark glass, no light-on-light text.
- Backdrop-blur must degrade gracefully where unsupported (`@supports` fallback
  to a solid near-white pill — never an unreadable transparent one).
- Do NOT remove/rename any rendered data element, fetch, conditional, or honest
  label. Zero fake/sample data. P&L sign-colors and "RELIANCE · NSE" display
  stay as-is.

## Verify
- `npm --prefix frontend run build` passes.
- No console errors on load.
- Manager will check in-browser: pills legible, motion smooth, text contrast on
  glass, safety posture (live + broker) both shown.

## Out of scope
- No data/logic changes, no new pages, no backend, no chart work.
- Do NOT commit to git — leave the change in the worktree for manager review.
  (Frontend is manager-owned; the manager diffs and lands it.)
