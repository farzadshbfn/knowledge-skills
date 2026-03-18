#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest"]
# ///
"""Run all skill tests."""
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.exit(__import__("pytest").main([str(Path(__file__).parent)] + sys.argv[1:]))
