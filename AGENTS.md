# Dependencies
- The project uses `uv`.
# Linting
## ruff
- After making changes
  - Run `uv run ruff format` to make sure files are correctly formatted.
  - Run `uv run ruff check` to catch lint errors.
## ty
  - Run `uv run ty check` to type check the code. It must report no diagnostics.
# Testing
- The project exclusively uses `pytest`.
- Prefer `monkeypatch` to `unittest.mock.patch`.
- Run tests using `uv run pytest -vvv`.