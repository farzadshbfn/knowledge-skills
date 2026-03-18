"""Shared test helpers: mock KB content builders."""

import sys
from pathlib import Path

# Make the scripts directory importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def note(name: str = "Test Note", desc: str = "A test note.") -> str:
    return f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\nContent here.\n"


def index(name: str = "Test - Index", desc: str = "Index for test topic.") -> str:
    return f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\nOverview.\n"


def skill(
    name: str = "test-skill",
    desc: str = "A test skill.",
    hint: str = "<arg>",
) -> str:
    return (
        f"---\nname: {name}\ndescription: {desc}\n"
        f'argument-hint: "{hint}"\n---\n\n# {name}\n\nInstructions.\n'
    )


def project_agent(
    name: str = "test-agent",
    desc: str = "A test agent.",
    tools: str = "Read, Glob",
    model: str = "opus",
    skills: list[str] | None = None,
) -> str:
    lines = [f"---\nname: {name}\ndescription: {desc}\ntools: {tools}\nmodel: {model}"]
    if skills:
        lines.append("skills:")
        for s in skills:
            lines.append(f"  - {s}")
    lines.append("---\n\nAgent body.\n")
    return "\n".join(lines)


def skill_agent(
    name: str = "test-subagent",
    desc: str = "A test subagent.",
    tools: str = "Read, Glob",
    model: str = "haiku",
    background: bool = True,
    skills: list[str] | None = None,
) -> str:
    bg = "true" if background else "false"
    lines = [
        f"---\nname: {name}\ndescription: {desc}\ntools: {tools}\n"
        f"model: {model}\nbackground: {bg}"
    ]
    if skills:
        lines.append("skills:")
        for s in skills:
            lines.append(f"  - {s}")
    lines.append("---\n\nSubagent body.\n")
    return "\n".join(lines)



def reference() -> str:
    return "# Reference\n\nPlatform-specific rules.\n"


def asset() -> str:
    return "---\nname: {{NAME}}\ndescription: {{DESCRIPTION}}\n---\n\n# {{TITLE}}\n"
