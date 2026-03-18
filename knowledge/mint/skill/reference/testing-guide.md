# Testing Guide for Skill Scripts

Mock filesystem boundaries with `unittest.mock`. Tests call logic functions directly (not `__main__`).

## Contents
- [Core pattern](#core-pattern)
- [Running tests](#running-tests)
- [Mock recipes](#mock-recipes)

## Core Pattern

```python
from unittest.mock import patch
from scripts.process import process

def test_normal_case():
    with patch("pathlib.Path.read_text", return_value='{"value": 42}'), \
         patch("pathlib.Path.write_text") as mock_write:
        result = process("any/path.json")
    assert result == {"result": 84}
    mock_write.assert_called_once()
```

Principles: mock at boundaries (`Path.read_text`, `Path.write_text`, `Path.exists`), test error paths (`FileNotFoundError`, malformed JSON), assert both return values and side effects.

## Running Tests

Each test suite should have a `run_tests.py` with inline pytest dependency:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest"]
# ///
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.exit(__import__("pytest").main([str(Path(__file__).parent)] + sys.argv[1:]))
```

```bash
# Single-file scripts (no pyproject.toml) — use run_tests.py entry point
uv run scripts/tests/run_tests.py -q

# MCP server projects (with pyproject.toml)
uv add --group test pytest && uv run pytest tests/
```

## Mock Recipes

```python
# Multiple files
def mock_read(self):
    return {"a.json": '{"a": 1}', "b.json": '{"b": 2}'}.get(str(self), "{}")
with patch("pathlib.Path.read_text", mock_read): ...

# Subprocess
from unittest.mock import MagicMock
mock_result = MagicMock(returncode=0, stdout="output")
with patch("subprocess.run", return_value=mock_result): ...

# File existence
with patch("pathlib.Path.exists", return_value=False): ...
```
