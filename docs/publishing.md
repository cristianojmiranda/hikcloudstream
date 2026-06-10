# Publishing to PyPI

## One-time setup

1. Create a [PyPI account](https://pypi.org/account/register/) if needed.
2. Create an API token at https://pypi.org/manage/account/token/ (scope: entire account or project `hikcloudstream`).
3. In GitHub repo **Settings → Secrets and variables → Actions**, add:
   - `PYPI_API_TOKEN` — the PyPI token (including `pypi-` prefix)
4. In GitHub repo **Settings → Environments**, create environment `pypi` (optional; used by the publish workflow).

## Release process

```bash
# bump version in pyproject.toml and src/hikcloudstream/__init__.py
# update CHANGELOG.md

uv run pytest tests/unit -v
uv run ruff check src tests
uv build

git add -A
git commit -m "chore(release): v0.1.x"
git tag v0.1.x
git push origin main --tags
```

Pushing a `v*` tag triggers [`.github/workflows/publish.yml`](../.github/workflows/publish.yml).

## Manual publish (local)

```bash
uv build
UV_PUBLISH_TOKEN=pypi-XXXX uv publish
```

Never commit tokens. Do not add tokens to the repository.
