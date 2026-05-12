"""Compatibility package alias for the renamed `sre_bot` package."""

from importlib import import_module
import sys


_sre_bot = import_module("sre_bot")
sys.modules[__name__] = _sre_bot
