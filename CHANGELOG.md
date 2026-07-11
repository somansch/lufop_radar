# Changelog

All notable changes to this integration are documented here.

## v1.2.1

First release verified against the real Lufop API with a live key. Several issues below only surfaced once real data and a real account's limits came into play.

### Fixed
- The country selector's option order was only actually alphabetical in English - German and French showed the same (English-sorted) order underneath correctly-translated labels. Each language now has its own sorted option order.
- Polling now respects the Lufop free plan's limits (200 requests/day, 10 requests/minute, 200 results/request): requests are throttled to stay under the per-minute cap, and each area/route's poll interval scales with how many requests it needs per poll (longer for routes with more sample points) to stay comfortably under the daily cap. Previously every entry polled every 60 seconds regardless of these limits.
- API errors now surface Lufop's actual error message (e.g. `country_not_allowed: This country is not available with the Free plan...`) instead of a bare, unhelpful HTTP status code - discovered because the free plan only allows France, Belgium, and Switzerland, and every other country in the picker fails with exactly this error on a free-plan key.
- Radar type filtering was silently discarding every radar. Live API responses return a numeric radar-model ID in the `type` field (e.g. `"18"`, `"40"`, `"148"`), not the `fixe`/`mobile`/`feu` strings this integration was built around - those were apparently only accurate for an older API version or different docs. Fixed/mobile/red-light is now classified from keywords in the `name` field instead (e.g. "Radar Fixe ...", "Radar Feu Rouge ..."), which is the one field that reliably carries this information.

## v1.2.0

### Removed
- Construction-zone radars are no longer tracked. This integration focuses on speed cameras only (fixed, mobile, red light).

### Changed
- Technical fields that used to carry Lufop's native French vocabulary are now English: the `type` attribute reports `fixed`/`mobile`/`redlight` instead of `fixe`/`mobile`/`feu`, and the `vitesse`/`azimut` attributes are renamed to `speed`/`azimuth`.
- The country field in the config wizard now shows full country names, sorted alphabetically, in the wizard's own language, instead of raw ISO codes.
- The "Number of sensors" / "Anzahl der Sensoren" option is now labelled "Maximum number of radars" / "Maximale Anzahl der Blitzer" / "Nombre maximum de radars".
- README is now English-only.

### Added
- French config-wizard translation. The wizard now auto-selects English, German, or French based on the Home Assistant user's language.

## v1.1.0

### Added
- **Route (waypoint) search mode**, ported from the sibling `blitzer` integration: search a corridor along a hand-drawn route instead of a single radius, with no external routing engine — waypoints are placed one map screen at a time, and radars are found by sampling points along the straight segments between them. Editing a route offers a menu to either revise its waypoints (reposition/remove each one) or jump straight to the corridor/type/optional settings.

### Changed
- The whitelist is now a comma-separated list of city names (matching the blacklist's syntax) instead of a regex.

## v1.0.0

Initial release: polls the free, officially-documented [Lufop](https://lufop.net) radar API for fixed/mobile/construction/red-light radars (construction-zone support was later removed in v1.2.0), exposed as dynamically-managed `geo_location` entities per configured area, plus a total-count sensor.
