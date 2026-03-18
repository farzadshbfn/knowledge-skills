# uv Scripting Guide for Skills

## Contents
- [PEP 723 inline metadata](#pep-723-inline-metadata)
- [Running scripts](#running-scripts)
- [Testable script layout](#testable-script-layout)
- [MCP vs scripts](#mcp-vs-scripts)
- [MCP server structure](#mcp-server-structure)

## PEP 723 Inline Metadata

Every skill script declares dependencies inline (no `pyproject.toml` needed):

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests<3", "rich"]
# ///
```

`dependencies` field **must always be present**, even if empty. Manage with `uv add --script example.py 'requests<3'`.

## Running Scripts

```bash
uv run script.py                      # basic
uv run script.py --verbose out.json   # with args
uv run --no-project script.py         # skip pyproject.toml
```

Prefer inline dependencies over `--with` for reproducibility. If a script needs a package, declare it in the script metadata rather than relying on `--with` at the call site.

## Testable Script Layout

Separate pure logic from CLI entry point — tests call functions directly:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
import json, sys
from pathlib import Path

def process(path: str) -> dict:
    """All logic here — no CLI concerns."""
    data = json.loads(Path(path).read_text())
    return result

if __name__ == "__main__":
    args = json.load(sys.stdin)
    print(json.dumps(process(args["path"])))
```

Script directory layout: `scripts/process.py` + `scripts/tests/test_process.py`

## MCP vs Scripts

| Factor | Script | MCP Server |
|--------|--------|------------|
| Token cost/call | ~300-500+ | ~50-100 |
| Complexity | Single-purpose | Multi-tool |
| State | Stateless | Stateful |
| Files | Single | Multi-file (uv project) |

Prefer MCP for complex/multi-tool ops (out-of-process, clean function signature). Prefer scripts for simple stateless ops.

## MCP Server Structure

Use a uv project with `pyproject.toml`. Keep `server.py` as thin registration — all logic in `tools/`:

```python
from mcp.server.fastmcp import FastMCP
from tools import file_tools

mcp = FastMCP("my-skill")

@mcp.tool()
def read_file(path: str) -> dict:
    """Use when you need to read and parse a project file."""
    return file_tools.read(path)
```

Tool descriptions: write from Claude's perspective (decision-oriented, not implementation-oriented).
