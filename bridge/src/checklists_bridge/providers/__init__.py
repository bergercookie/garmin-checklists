"""Task providers.

Importing this package registers every built-in provider in
:data:`checklists_bridge.providers.registry.REGISTRY`.
"""

from __future__ import annotations

from checklists_bridge.providers import (  # noqa: F401  (registration side effect)
    local,
    trilium,
    vikunja,
)
from checklists_bridge.providers.base import (
    EditableTaskProvider,
    ProviderAuthError,
    ProviderError,
    ProviderUnavailableError,
    SourceNotFoundError,
    TaskProvider,
)
from checklists_bridge.providers.registry import REGISTRY, ConfigField, ProviderSpec

__all__ = [
    "REGISTRY",
    "ConfigField",
    "EditableTaskProvider",
    "ProviderAuthError",
    "ProviderError",
    "ProviderSpec",
    "ProviderUnavailableError",
    "SourceNotFoundError",
    "TaskProvider",
]
