# LaunchWitness

> Describe your business. LaunchWitness launches it on GoDaddy and proves everything works before your first customer arrives.

Built for the GoDaddy Inclusive Innovation Hackathon 2026 (working name).

- Product spec: [`docs/SPEC.md`](docs/SPEC.md)
- Build plan: [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md)
- Status: [`docs/PROGRESS.md`](docs/PROGRESS.md)
- How it was built with Claude Code: [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md) and the combined session replay at `/build` on the live app

## Setup

```bash
cp .env.example .env   # fill in locally; never commit
```

Run and test commands are listed in [`CLAUDE.md`](CLAUDE.md) under "Commands".

## Building the session replay

```bash
bash scripts/build-replay.sh   # -> replay/build.html (one page, all sessions, secrets redacted)
```
