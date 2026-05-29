"""
services/providers/__init__.py
------------------------------
Provider registry for OpenClaw automation.

Each provider implements the ProviderAgent interface and encapsulates
all platform-specific browser automation logic (auth, navigation,
export workflow, selectors).

Current providers:
  - CartaProvider  — cap table / holdings export automation
"""

from .base import ProviderAgent
from .carta import CartaProvider

__all__ = ["ProviderAgent", "CartaProvider"]
