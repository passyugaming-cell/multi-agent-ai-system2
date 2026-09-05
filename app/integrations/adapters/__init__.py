from app.integrations.adapters.rest_api import RestApiAdapter
from app.integrations.adapters.webhook import WebhookAdapter
from app.integrations.adapters.google_sheets import GoogleSheetsAdapter
from app.integrations.registry import integration_registry

integration_registry.register("rest_api", RestApiAdapter())
integration_registry.register("webhook", WebhookAdapter())
integration_registry.register("google_sheets", GoogleSheetsAdapter())

__all__ = [
    "RestApiAdapter",
    "WebhookAdapter",
    "GoogleSheetsAdapter",
]
