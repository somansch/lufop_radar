# Changelog

All notable changes to this integration are documented here.

## v2.0.0

### Added
- **Configurable polling interval** ("Update interval", in minutes) for every area/route, replacing the previous fixed, quota-derived interval. Defaults to 10 minutes for an area; for a route, to the route's sample-point count × 8 minutes (shown to you, recalculated live if you adjust the corridor width). Setting it to **0** disables automatic polling entirely for that entry.
- **`lufop_radar.refresh` action** ("Lufop Refresh"), for on-demand polling - most useful for entries with a manual-only (`0`) update interval, e.g. triggered from an automation, but works for any entry. Immediately fetches the latest radars, updates that entry's `geo_location` entities exactly like a normal poll, and returns the radars found so an automation can use them directly (e.g. in a notification) without a separate template step. See the README's new automation example.
- The route wizard's corridor-width step is now separate from the rest of the route's settings, so the following step can show an accurate, live "N sample points / requests per poll at this corridor width" explanation and a matching suggested update interval. An "Adjust corridor width instead of saving" option loops back to revise it without redrawing the whole route.

### Changed
- Entries created before the update-interval option existed keep their previous (quota-safe, ~10 min × requests-per-poll) polling behavior until next saved via Configure, rather than silently switching to the new default.
- When update interval is `0`, entities start empty instead of the integration making an API call on every Home Assistant startup/reload - the whole point of manual-only mode is avoiding automatic requests.
- The total-count sensor's name no longer has a stray German word ("Anzahl") left over from an earlier translation pass.

## v1.2.2

Second round of live-testing fixes, plus entity display and dashboard polish, from configuring real areas in Strasbourg and Paris.

### Added
- README now includes a "Dashboard Examples" section with screenshots and the actual map/markdown card configuration used for them, matching the sibling `blitzer` integration's README structure.

### Changed
- README now states explicitly that only the free plan's country coverage (France, Belgium, Switzerland) has been tested, and all examples use French/Belgian/Swiss cities instead of German ones.
- Entity friendly names now use the radar's city and street (e.g. "Lufop Paris Strasbourg, M 35") instead of Lufop's raw radar name.
- Every radar now gets a generated round road-sign picture as its `entity_picture` - the speed limit for speed cameras, a traffic-light emoji for red-light cameras - which both the entity itself and the map card's marker render. The map card previously showed no usable icon at all for MDI icons on geo_location markers, falling back to text initials of the entity name.
- The `flash_direction` attribute now reports readable `front`/`back`/`both` instead of Lufop's raw `F`/`B`/`D` codes (per Lufop's docs: F = Front, B = Back, D = Double sens/both).

### Removed
- "Covoiturage" (carpool/HOV-lane) cameras with no speed limit are now dropped entirely instead of showing up as unlabelled fixed cameras. These check lane occupancy, not speed, and always report an empty "vitesse" by design (confirmed against a live example on Lufop's own site) - not useful for a speed-camera integration.

### Fixed
- "Chantier" radars (mobile radar units deployed in roadwork zones - Lufop's own term, not the roadwork itself) were being misclassified as fixed cameras. Some countries, notably France, have no separate "Mobile" listing at all and report these mobile deployments only as "Chantier", so this was silently miscategorizing (and, before that, dropping entirely) real mobile-radar data. "Chantier" now counts as "mobile", alongside countries that do report literal "Mobile" entries (e.g. Belgium, Switzerland).

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
