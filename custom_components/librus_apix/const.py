"""Constants for the Librus APIX integration."""

from datetime import timedelta

DOMAIN = "librus_apix"
DEFAULT_NAME = "Librus"

# Configuration keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Update intervals
SCAN_INTERVAL = timedelta(hours=2)

# Default values
DEFAULT_MESSAGES_COUNT = 10

# Ile dni lekcyjnych pokazuje czujnik planu
DEFAULT_PLAN_DAYS = 5
