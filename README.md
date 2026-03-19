# Knowledge Skills

![Claude](https://img.shields.io/badge/Claude-compatible-D97757?logo=claude&logoColor=fff)
![Cursor](https://img.shields.io/badge/Cursor-compatible-007ACC?logo=cursor&logoColor=fff)

![Knowledge Skills](assets/banner.png)

You read an article, learn something new, move on. A month later you've forgotten half of it. Claude forgot all of it the moment the conversation ended.

These skills give you a shared knowledge base. When you learn something, Claude learns it too, checks it against what you both already know, and keeps it around for next time.

> Looking for the installable plugin? See [knowledge-plugin](https://github.com/farzadshbfn/knowledge-plugin).

## Install

```bash
npx skills add farzadshbfn/knowledge-skills
```

Then run `/kb-bootstrap` to set up your first knowledge base.

## Why This Exists

Tech moves fast. New frameworks, new conventions, a constant stream of articles and release notes. Even when you *do* read something useful, it's gone from your head a month later.

LLMs can help, but they forget everything between conversations and their training data lags behind. Context windows are expensive and finite. You end up re-explaining the same things, re-looking-up the same references, losing the insights you already earned.

These skills fill that hole:

- You only learn what you don't already know. New information is checked against your existing knowledge, so you're not re-reading things you've already internalized.
- Knowledge survives across conversations, projects, and machines. Plain markdown files you own.
- Topics you keep coming back to get flagged as skill candidates. Your most-used knowledge turns into dedicated, reusable skills without manual curation.
- Retrieval is progressive. It reads just enough to answer the question, not your entire KB. Context stays cheap.

## Skills

| Skill | Purpose |
|-------|---------|
| `/kb-learn` | Learn from articles, research topics, fix KB errors |
| `/kb-find` | Look up existing knowledge with progressive, token-efficient loading |
| `/kb-compact` | Split oversized notes, unify terminology, fix indexes |
| `/kb-mint` | Convert KB topics into skills, package as distributable plugins |
| `/kb-view` | Local web renderer with fuzzy search, markdown rendering, and knowledge graph |
| `/kb-monitor` | Track access patterns, surface skill candidates, check skill health |
| `/kb-bootstrap` | First-time setup, run once per project |

## How It Works

### Learn

`/kb-learn` runs a multi-agent pipeline:

1. **Scouter** finds related notes in your KB (including counter-evidence via `--challenge`)
2. **Searcher** pulls context from the web
3. **Assessor** evaluates claims against your existing knowledge + web evidence
4. New or updated notes are written with proper cross-references and changelog entries

```
/kb-learn article <url>          # Extract and assess claims from an article
/kb-learn topic "raft consensus" # Research a topic, fill gaps in your KB
/kb-learn fix "X actually works like Y"  # Correct a mistake
```

After learning, ask Claude to summarize what it found, explain trade-offs, or compare against what you already knew.

### Find

`/kb-find` progressively loads only what's relevant:

```
Tier 1 → Topic tree (names + descriptions only)
Tier 2 → Frontmatter scan (first 15 lines of candidates)
Tier 3 → TOC + targeted sections
Tier 4 → Full note read (only when necessary)
```

A lookup in a 10,000-line KB might only load 50 lines into context. Challenge mode (`--challenge`) looks for contradicting evidence.

### View

`/kb-view` starts a local HTTP server with a single-page app:

- Sidebar tree navigation across all configured KBs
- Fuzzy search across all notes
- Markdown rendering with syntax highlighting and Mermaid diagrams
- Interactive knowledge graph (d3-based) showing connections between notes
- Light/dark/system theme

![Knowledge graph](assets/kb-graph.png)

### Compact and Evolve

`/kb-compact` keeps your KB healthy as it grows. It splits large notes, merges duplicates, unifies terminology, and rebuilds indexes. `--deep` mode traverses the entire KB bottom-up.

### From knowledge to skills

Access patterns are tracked across conversations. When topics keep coming back, they're flagged as skill candidates. These are topics mature enough to be a dedicated skill rather than a loose collection of notes.

`/kb-mint` converts those candidates into standalone skills. The pipeline: raw notes, then structured knowledge, then reusable skill.

## Multi-KB support — the proximity principle

A single centralized KB works until you're juggling multiple domains, then you're loading irrelevant context every time.

Multi-KB lets you co-locate knowledge with the domain it serves:

```json
// .claude/knowledge-base/config.json
{
  "kb_roots": [
    { "name": "core", "path": "./knowledge" },
    { "name": "frontend", "path": "./frontend/knowledge" },
    { "name": "infra", "path": "./infra/knowledge" }
  ]
}
```

Each KB lives next to its domain. `/kb-find` searches the most relevant KB first, so you get fewer tokens loaded and more relevant results. When a concept spans domains, `@kb-name/path` cross-references link them without duplicating content.

Tighter scoping means less noise for the progressive loader to filter through. Three focused domain KBs with cross-links are faster and more precise than one 200-note general KB. Everything stays connected, but retrieval is cheaper.

## Architecture

```
knowledge/
  learn/       Multi-agent learning pipeline (scouter, searcher, assessor)
  find/        Progressive 4-tier loader with deterministic Python scripts
  compact/     KB restructuring and health checks
  mint/        Skill conversion and plugin packaging
  view/        Local web renderer (HTTP server + SPA + d3 graph)
  monitor/     Access tracking and skill candidate analysis
  bootstrap/   First-time project setup
```

Data retrieval is near-deterministic. Python scripts handle indexing, tree building, validation, and access tracking. The LLM orchestrates workflows and makes judgment calls. The scripts do the rest.

---

Built by [Farzad Sharbafian](https://github.com/farzadshbfn)

[![Follow on X](https://img.shields.io/badge/Follow-@farzadshbfn-000000?logo=x&logoColor=white)](https://x.com/farzadshbfn) · I post about AI, dev tools, and making agents actually useful
