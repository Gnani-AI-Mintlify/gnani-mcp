## Contributing

Thank you for your interest in contributing to gnani-mcp!

### Setting up the development environment

```bash
git clone https://github.com/gnani-ai/gnani-mcp.git
cd gnani-mcp

uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Running tests

```bash
pytest -q
```

### Code style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check lints
ruff check src/ tests/

# Format
ruff format src/ tests/
```

### Pull Request Guidelines

- Keep PRs focused — one feature or bug fix per PR.
- Add or update tests for any new tool or API change.
- Update `README.md` if you add new tools or configuration options.
- Run `ruff check` and `pytest` locally before submitting.
