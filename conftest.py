"""
conftest.py – pytest root configuration.

Automatically adds the repo root to sys.path so that core, signals,
reports, and notifier packages are importable from any test file
without each test needing its own sys.path.insert() call.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
