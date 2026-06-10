# Contributing

Thanks for helping improve **hikcloudstream**. This project is early-stage (0.x); APIs may change.

## Setup

```bash
git clone https://github.com/cristianojmiranda/hikcloudstream.git
cd hikcloudstream
uv sync --all-extras
```

## Run tests

```bash
uv run pytest tests/unit -v
uv run ruff check src tests
uv run mypy src/hikcloudstream
```

Integration tests (live Hik-Connect account) are optional:

```bash
export HIK_CONNECT_USER=...
export HIK_CONNECT_PASSWORD=...
uv run pytest -m integration  # when added
```

Never commit credentials or device serials from your environment.

## Releases

See [docs/publishing.md](docs/publishing.md) for PyPI publish steps.

## Pull request checklist

- [ ] English for code, comments, CLI help, and user-facing errors
- [ ] No secrets, real account names, or private URLs in the diff
- [ ] Unit tests for behavior changes (rtp, crypto, probe logic)
- [ ] Public API changes documented in `CHANGELOG.md`
- [ ] `uv run ruff check` and `uv run pytest tests/unit` pass

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, etc.

## AI-assisted changes

Read [AGENT.md](AGENT.md) before editing. Keep diffs focused; match existing module layout.
