# Agent directives

> **Entry point for LLM agents and contributors working in this repository.**

## What this repo is

**hikcloudstream** is an unofficial Python SDK for **Hik-Connect cloud cameras**:

- REST login, device list, cloud snapshots
- Live video via **cloud VTM relay** (not LAN RTSP, not P2P)

It is a **public open-source library** (Apache-2.0), not a sandbox experiment.

## Language policy (non-negotiable)

**All code artifacts must be in English:**

- Identifiers, docstrings, comments, CLI help, error messages, HTTP viewer HTML
- README and docs inside the repo
- Commit messages (Conventional Commits)

You may chat with the user in their language; never mirror it in the codebase.

## Sensitive data policy

**Never commit:**

- Real usernames, passwords, device serials, validate codes
- APK decompile trees or proprietary SDK blobs
- Condominium-specific names or private regional host examples beyond public `api.hik-connect.com`

Use `.env` locally (gitignored). Examples use `user@example.com` placeholders only.

## Architecture map

| Module | Responsibility |
|--------|----------------|
| `src/hikcloudstream/client.py` | REST API, login, list, snapshot |
| `src/hikcloudstream/capture.py` | Cloud snapshot AES decrypt |
| `src/hikcloudstream/stream/session.py` | VTM session, `LiveStreamSession`, record/capture helpers |
| `src/hikcloudstream/stream/probe.py` | Auto stream type (substream vs main) |
| `src/hikcloudstream/stream/rtp.py` | RTP → Annex B |
| `src/hikcloudstream/stream/crypto.py` | Encrypted NAL decrypt |
| `src/hikcloudstream/stream/sinks/` | MPEG-TS, MJPEG, HTTP viewer |
| `src/hikcloudstream/cli/` | Thin CLI over public API only |

Stable exports live in `src/hikcloudstream/__init__.py` and `src/hikcloudstream/stream/__init__.py`.

## How to change things safely

1. Read surrounding code; match naming and patterns.
2. Keep CLI and examples on the **public API** — no direct `pyezvizapi` in `cli/`.
3. Breaking API changes → update `CHANGELOG.md` and README examples.
4. Prefer typed exceptions from `exceptions.py` over bare `RuntimeError`.
5. Unit-test protocol logic (RTP, crypto) with redacted fixtures — no live credentials in CI.

## Common pitfalls

| Issue | Cause | Note |
|-------|-------|------|
| Black video on main stream | Proprietary RTP on some DVR channels | Auto substream (`stream=2`) |
| VTDU token failure | Wrong auth path for Hik-Connect | Primary: `POST /api/user/token/get` |
| MJPEG viewer + encryption | Decrypt not wired in viewer | Use `validate_code` with record/snapshot only |
| N viewers = N VTM sessions | One TCP session per consumer | Document fan-out / HLS for scale |

## Testing expectations

- `tests/unit/` must pass in CI without secrets
- Integration tests: `@pytest.mark.integration`, env-gated only
- Run `uv run ruff check src tests` before finishing

## Routing

| Need | Go to |
|------|--------|
| User-facing overview | [README.md](README.md) |
| Streaming API detail | [docs/streaming.md](docs/streaming.md) |
| Maintainer blueprint | [docs/MAINTAINER_BLUEPRINT.md](docs/MAINTAINER_BLUEPRINT.md) |
| Legal / OSS notes | MAINTAINER_BLUEPRINT § License |

## Conflict resolution

1. User explicit choice
2. This `AGENT.md` for repo-specific rules
3. Target module conventions
4. Generic best practice

If the developer also uses the **pkb** workspace, engineering discipline from `pkb/CLAUDE.md` applies unless it conflicts with this file.
