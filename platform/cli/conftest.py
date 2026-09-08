"""Pytest path setup: make the grader package importable from the tests.

A conftest at platform/cli puts this directory on sys.path (rootdir-relative
import), so tests import `grader` exactly the way the CLIs do.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
