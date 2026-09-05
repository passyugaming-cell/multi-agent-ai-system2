import logging
from typing import Dict
from app.integrations.exceptions import IntegrationError
from app.integrations.interfaces import IntegrationAdapter

logger = logging.getLogger(__name__)


class IntegrationRegistry:
    """Registry for managing external provider adapters dynamically."""

    def __init__(self) -> None:
        self._adapters: Dict[str, IntegrationAdapter] = {}

    def register(self, provider_key: str, adapter: IntegrationAdapter) -> None:
        key = provider_key.lower().strip()
        if key in self._adapters:
            logger.warning("Overwriting existing adapter for provider: %s", key)
        self._adapters[key] = adapter
        logger.info("Registered integration adapter for provider: %s", key)

    def get_adapter(self, provider_key: str) -> IntegrationAdapter:
        key = provider_key.lower().strip()
        adapter = self._adapters.get(key)
        if not adapter:
            raise IntegrationError(f"No integration adapter registered for provider '{provider_key}'")
        return adapter

    def is_registered(self, provider_key: str) -> bool:
        return provider_key.lower().strip() in self._adapters

    def list_providers(self) -> list[str]:
        return list(self._adapters.keys())


integration_registry = IntegrationRegistry()
