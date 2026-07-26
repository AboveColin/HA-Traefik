"""Constants for the Traefik integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "traefik"

CONF_METRICS_URL: Final = "metrics_url"
CONF_ROUTERS: Final = "routers"
CONF_VERIFY_SSL: Final = "verify_ssl"

# Traefik is a local service and the API is cheap, but the numbers it reports
# only change when configuration changes, so once a minute is plenty.
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=1)

MANUFACTURER: Final = "Traefik Labs"
