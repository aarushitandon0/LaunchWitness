# Build log — how LaunchWitness was built with Claude Code

One entry per Claude Code session, newest last. This is what judges read to understand the process; the full transcripts are in the combined replay at `/build`.

## Template (copy for each session)

```
### Session N — YYYY-MM-DD — <short title>
- Goal: <milestone + acceptance criteria targeted>
- Asked Claude to: <1–2 lines>
- Claude built: <files/features>
- I changed / rejected: <what the human decided or corrected>
- Result: <ACs passed, tests, what works now>
- Next: <one line>
```

---

### Session 0 — 2026-11-14 — Ideation and spec
- Goal: settle the idea and plan before writing code.
- Worked with Claude (chat) to pressure-test the idea: dropped "rollback after launch" as the hero after realizing that in a setup we control, little breaks post-launch; moved repair into the launch itself; kept light monitoring.
- Output: `docs/SPEC.md`, `docs/BUILD_PLAN.md`, `CLAUDE.md`.
- Next: M0 scaffold.
