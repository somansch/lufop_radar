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
