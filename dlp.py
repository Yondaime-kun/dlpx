#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thin entry point – delegates to the dlpx package.
All original functionality is preserved in the split modules under dlpx/.
"""

from dlpx.cli import main

if __name__ == "__main__":
    main()