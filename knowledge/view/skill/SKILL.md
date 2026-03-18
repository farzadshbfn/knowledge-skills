---
name: kb-view
description: Opens the KB viewer in the browser. Starts a local HTTP server that renders all configured knowledge bases with working links, fuzzy search, and knowledge graph visualization.
user-invocable: true
---

# /kb-view — KB Viewer

## 0. Prerequisites

Check for KB config at `.claude/knowledge-base/config.json`. If missing, tell user: "KB is not configured. Run `/kb-bootstrap` to set up your knowledge base." and stop.

## 1. Suggest Running in a Separate Terminal

Use `AskUserQuestion` to strongly recommend the user runs the server themselves in a separate terminal window. The server runs continuously and is more responsive when not managed by Claude.

Present the command:

```
uv run ${CLAUDE_SKILL_DIR}/scripts/serve.py --project-root .
```

Options:
- **"I'll run it myself"** (recommended) → Give the command, tell them to open http://127.0.0.1:8787, and stop.
- **"Run it for me"** → Continue to Step 2.

## 2. Start the Viewer (fallback)

If the user wants Claude to run it:

1. Run in **background** Bash: `uv run ${CLAUDE_SKILL_DIR}/scripts/serve.py --project-root .`
2. Open browser: `open http://127.0.0.1:8787`
3. Tell user: "KB viewer running at http://127.0.0.1:8787 — press Ctrl+C to stop."

Custom port: add `--port <PORT>`.

## 3. Architecture

- `scripts/serve.py` — ThreadingHTTPServer. Reads KB config, delegates tree building to `kb_loader.py`, serves markdown with parsed frontmatter and resolved `@kb-name` links. SPA fallback: all non-API paths serve `index.html`.
- `scripts/index.html` — Single-page app. Sidebar tree, fuzzy search, markdown rendering (marked.js + highlight.js + mermaid), `pushState` URL routing, breadcrumb, light/dark/system theme.
- `scripts/graph.js` — d3-based knowledge graph. Hierarchical KB layout, hover glow, edge flow animation, controls panel, focus-on-node.

## 4. API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | HTML viewer |
| `GET /api/tree` | KB tree (JSON via kb_loader.py) |
| `GET /api/file?path=<rel>` | Markdown file with parsed frontmatter |
| `GET /api/config` | Raw KB config |
| `GET /api/search?q=<query>` | Fuzzy search across KB files |
| `GET /api/graph` | File link graph (nodes + edges) |
| `GET /*` | SPA fallback (index.html) |

## 5. Running Tests

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/tests/run_tests.py -v
```
