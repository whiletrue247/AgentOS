#!/usr/bin/env python3
"""
AgentOS v5.0 — Quick Start Entry Point
=========================================
Alias for main.py, as referenced in README.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import main  # noqa: E402

if __name__ == "__main__":
    main()
