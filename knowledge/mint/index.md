---
name: Minting - Index
description: Index for the minting skill — converts KB topics into skills, packages skills into plugins, and prepares them for Cowork.
---

# Minting - Index

## Overview

Minting automates three stages of the KB-to-distribution pipeline:

1. **Skill conversion** — Extract actionable "how" content from KB concept notes into a structured skill folder
2. **Plugin packaging** — Bundle related skills into a namespaced plugin directory with manifest
3. **Cowork readiness** — Add Cowork-specific considerations (connectors, marketplace labels)

## Skill

Full procedures, templates, and reference files: [`skill/SKILL.md`](skill/SKILL.md)

### Skill Contents

**References:**

| Reference | Purpose |
|-----------|---------|
| [skill-conversion-guide](skill/reference/skill-conversion-guide.md) | Step-by-step KB topic to skill conversion procedure |
| [skill-authoring-guide](skill/reference/skill-authoring-guide.md) | Best practices for writing effective SKILL.md files |
| [plugin-packaging-guide](skill/reference/plugin-packaging-guide.md) | Skills to plugin directory — namespacing, manifest, Cowork |
| [uv-scripting-guide](skill/reference/uv-scripting-guide.md) | PEP 723 inline metadata, testable script layout, MCP vs scripts |
| [testing-guide](skill/reference/testing-guide.md) | Testing skill scripts with unittest.mock, filesystem mocking patterns |

**Assets:**

| Asset | Purpose |
|-------|---------|
| [SKILL.md.template](skill/assets/skill-scaffold/SKILL.md.template) | Scaffold template for new skill SKILL.md files |
| [plugin.json.template](skill/assets/plugin-scaffold/plugin.json.template) | Scaffold template for plugin manifest |

## Related Topics

| Topic index | Summary |
|-------------|---------|
| [Monitoring](../monitor/index.md) | KB usage monitoring — detects skill candidates, delegates conversion to minting |
