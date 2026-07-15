"""Connector factory — routes a source name to the correct connector instance.

Connectors are lazy-initialised so:
- credentials are only loaded when the connector is first requested
- a missing third-party package (jira, atlassian-python-api) never prevents
  the rest of the backend from starting up

Supported sources: "jira", "confluence"
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("mcp_server.services.connector_factory")

# Singleton cache — each connector is initialised only once per process.
_connector_cache: dict[str, Any] = {}


class ConnectorFactory:
    """Return an initialised connector by source name."""

    @staticmethod
    def get_connector(source: str) -> Any:
        """Return a cached, ready-to-use connector.

        Parameters
        ----------
        source:
            ``"jira"`` or ``"confluence"``

        Raises
        ------
        ValueError
            If *source* is not one of the supported values.
        """
        if source in _connector_cache:
            return _connector_cache[source]

        if source == "jira":
            # Lazy import — only loads the jira package when first called
            from mcp_server.tools.jira import JiraConnector
            connector: Any = JiraConnector()

        elif source == "confluence":
            # Lazy import — only loads atlassian-python-api when first called
            from mcp_server.tools.confluence import ConfluenceConnector
            connector = ConfluenceConnector()

        else:
            raise ValueError(
                f"Unknown connector source: '{source}'. "
                "Supported sources: jira, confluence."
            )

        _connector_cache[source] = connector
        logger.info("Initialised connector for source: %s", source)
        return connector
