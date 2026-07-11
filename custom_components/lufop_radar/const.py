DOMAIN = "lufop_radar"
CONF_COUNTRY = "country"
CONF_BLACKLIST = "blacklist"

TYPE_FIXED = "fixe"
TYPE_MOBILE = "mobile"
TYPE_REDLIGHT = "feu"

# ISO country codes Lufop documents as supported. The selector shows each
# one's localized name via the "country" translation key instead of the raw
# code - but a select selector's option *order* is fixed by the Python list
# below, it does NOT get re-sorted client-side by the translated label. So
# "alphabetical" only holds per language if we hand it a differently-ordered
# list per language.
#
# COUNTRIES is the canonical set of codes (English order, used as the
# fallback for any language without its own entry below).
COUNTRIES = [
    "ad", "au", "be", "bg", "ca", "cz", "fi", "fr", "de", "ie",
    "it", "lv", "lu", "ma", "nl", "nz", "no", "pl", "pt", "es",
    "se", "ch", "ae", "gb",
]

# Same codes, reordered alphabetically by each language's own country name
# (translations/<lang>.json's selector.country.options has the actual
# names). Pitfall for later: adding a new language means adding BOTH a new
# translations/<lang>.json AND a new entry here - the config wizard's
# per-language translation alone only changes the labels, not the order, so
# a language missing from this dict silently falls back to English order.
COUNTRY_ORDER_BY_LANGUAGE = {
    "en": COUNTRIES,
    "de": [
        "ad", "au", "be", "bg", "de", "fi", "fr", "ie", "it", "ca",
        "lv", "lu", "ma", "nz", "nl", "no", "pl", "pt", "se", "ch",
        "es", "cz", "ae", "gb",
    ],
    "fr": [
        "de", "ad", "au", "be", "bg", "ca", "ae", "es", "fi", "fr",
        "ie", "it", "lv", "lu", "ma", "no", "nz", "nl", "pl", "pt",
        "gb", "se", "ch", "cz",
    ],
}

CONF_SEARCH_MODE = "search_mode"
SEARCH_MODE_AREA = "area"
SEARCH_MODE_ROUTE = "route"
CONF_WAYPOINTS = "waypoints"
CONF_CORRIDOR_WIDTH = "corridor_width"
DEFAULT_CORRIDOR_WIDTH = 300

# How often this entry polls Lufop, in minutes. User-configurable per entry -
# 0 means "never automatically", relying entirely on the "refresh" service
# instead (e.g. triggered from an automation). The suggested defaults below
# are a starting point, not a hard quota-safe limit - anyone running several
# areas/routes on the same key (or wanting more headroom under the free
# plan's 200 requests/day) needs to raise this themselves; see the README's
# rate-limit section.
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_AREA_UPDATE_INTERVAL = 10
# Multiplied by the route's *sample*-point count (see route.py), not its raw
# waypoint count - a poll queries once per sample point, and how many of
# those a given set of waypoints produces depends on the corridor width too
# (e.g. two waypoints 2km apart with a 300m corridor already interpolates
# to 7 sample points: int(2000 // 300) + 1), so the request volume - and
# thus the quota-safe default - isn't just "one request per waypoint".
DEFAULT_MINUTES_PER_ROUTE_REQUEST = 8
UPDATE_INTERVAL_MANUAL = 0

SERVICE_REFRESH = "refresh"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
