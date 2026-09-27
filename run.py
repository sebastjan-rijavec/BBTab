#!/usr/bin/env python3
"""Convenience launcher: `python3 run.py [file.bbtab]`."""

import sys

from bbtab.app import main

if __name__ == "__main__":
    sys.exit(main())
