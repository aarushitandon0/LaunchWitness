# S19: landing page motion

Landing page only. Same copy, same colours (existing tokens only), same routes, ids and `data-testid`s.

## What changed
Files: `frontend/src/Landing.tsx`, `frontend/src/LandingProof.tsx` (pulse only), new `frontend/src/landing/*`
(`DecodeText.tsx`, `FlowLines.tsx`, `PromiseBeam.tsx`, `PanelCap.tsx`, `landing-motion.css`), `scripts/shoot_s19.js`,
`scripts/s19_verify.js`, screenshots, this note.

| Effect | Where | Reduced motion | Turn it off |
|---|---|---|---|
| Decode reveal (letters settle left to right, 0.8-0.9 s). Real text stays in the DOM; the scramble is a CSS `::after` layer, so screen readers and `textContent` see the real words | hero headline (on load), every section heading (once, on entering the screen) | no scramble | `DECODE_ON = false` in `landing/DecodeText.tsx` |
| Words fade in one by one | hero sub-copy, section lead paragraphs | text shown at once | use a plain `<p>` in `SectionHead` / hero |
| Hero stack assembles: six layers drop in with a soft spring bottom to top, white plate last, check draws itself, lime chip pops 0.8 to 1 | `HeroShape` | final state at once | remove the `initial` props in `HeroShape` |
| Ring sways, lime ball circles it (SMIL), orange dot drifts | `HeroShape` + `.ring-sway`, `.dot-drift` | static | delete those two classes |
| Flowing light-lines (4 SVG strokes, 3 glowing dots) | `FlowLines`, first child of the hero card | static lines, no dots | remove `<FlowLines />` |
| Pointer tilt, max 6 degrees, mouse + hover:hover only | `Landing` (`onMove`) | off | remove `onPointerMove` |
| Hero card rounds a little more + exploded layers as the dark panel slides over | scroll-linked `borderRadius`, `ys` | none | set `radius` range to `[r0, r0]` |
| Dark panels: rounded top edge flattens as the panel reaches the top | `PanelCap` (scaleY) | static | remove `<PanelCap />` |
| Proof: a glow travels hop 01 to 06 when the section first appears (looks only; never marks a hop done) | `LandingProof` + `.hoptrack-pulse` | hidden | remove `data-pulse` |
| Promises: list with a lime beam and small burst on the active row (hover and scroll). Phones: plain list, active row highlighted | `PromiseBeam` | no beam, all rows full strength | `display:none` on `.promise-beam` |
| Check any address: scan line while checking; result rows appear one by one | CSS on `.check-card.is-busy`, `.check-result .findings` | none | delete that CSS block |
| Security ticks draw in; cards lift on hover | `SecurityList`, CSS | ticks complete, no lift | delete that CSS block |

Reveals now play once (`once: true`); "How it works" keeps its old repeating reveal (`repeat`).

## Known limits / things I did not do
- All dark sections are the same `--ink`, so "panels sliding over each other" can only show as a hairline arc (`--ink-line`) at each panel's top edge. I did not add a lighter panel colour (colour scheme untouched). The effect is quiet by design.
- The detail panel under the proof track still fades in with the existing CSS animation; no `AnimatePresence` cross-fade, because two panels in the DOM at once would break the e2e text selectors.
- "Watch" section: only the shared reveal and the hover lift; no new playhead (left as is).
- "Built on GoDaddy" frosted strip (optional item 7): not done, you asked to be asked first.
- CSP: no CSP header is set on the app host (Caddyfile.prod); everything added is inline SVG/CSS/JS bundled in the page's own script, no external fonts, images or scripts.
