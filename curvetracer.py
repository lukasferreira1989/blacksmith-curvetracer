#!/usr/bin/env python3
"""Ponto de entrada para empacotamento (PyInstaller) e execução direta."""

import multiprocessing
import sys

from src.gui import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
    sys.exit(0)
