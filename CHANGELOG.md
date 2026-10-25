# Changelog

All notable changes to this integration are documented here.

## v2.2.2

**Lufop Radar is no longer developed.** Its successor is [TomTom](https://github.com/somansch/tomtom), with Lufop's speed cameras built in and TomTom's own jams, closures, roadworks, accidents and road weather in more than 70 countries, blitzer.de's cameras, a route planner on the card and 30 languages. Your Lufop key works there too. Lufop Radar keeps working as it is, but gets no new features.

## v2.2.1

### Changed
- **A wrong API key is caught on the form.** Setting up an area or a route saved the key unchecked, so a typo only turned up afterwards, as a prompt to enter the key again. The last step of both now asks Lufop about the key first - the same check the reauth step makes, which costs no quota - and when the key is refused, the form comes back with everything as it was typed, so only the key needs fixing. A Lufop that cannot be reached says so, instead of calling a good key wrong. **Configure** checks the key the same way when it is changed, and saves without asking when it is not, so the other settings can still be changed while Lufop is out of reach. Suggested in the HACS review.

## v2.2.0

### Added
- **The API key is checked, and a rejected one asks for a new key.** Until now nothing ever verified it: Lufop's radar endpoint answers a wrong key, an empty key and no key at all with a plain `200` and real data - measured against the live API, for every country tried - so a key that had been revoked simply went on working, and any other failure was retried forever. Lufop's own `format=meta` call is the one place the key is looked at; it answers `401 {"error": "unauthorized"}` and, per Lufop's documentation, costs no quota. It now runs once per setup, and a rejection raises `ConfigEntryAuthFailed`, which opens Home Assistant's own **reauthentication** dialog. The new key is offered to Lufop before it is saved, so a typo is refused on the spot rather than stored. A `401`/`403` from the radar endpoint would do the same, for the day Lufop starts enforcing it there.

### Fixed
- **Radars stayed on the map through an outage.** A failed poll leaves the previous data in place, and the markers were not tied to the poll's success in any way - so every radar went on reporting its last known position as though it were current, while the count sensor correctly went unavailable. For an integration people use while driving, that was the wrong way round. Each radar is now a `CoordinatorEntity` and goes unavailable with its area, coming back with the next poll that succeeds.

### Changed
- **Entities are identified by the config entry rather than by its display name.** Every unique id used to contain the name, so renaming an area changed all of them at once and Home Assistant saw a completely new set of entities while the old ones stayed behind as orphans. Renaming an entry is safe now. The generated entity ids get tidier with it - `sensor.lufop_paris_total` rather than `sensor.lufop_radar_lufop_radar_paris_total`.
- **The count sensor is a proper `SensorEntity`.** It sat on the sensor platform without being one: the value came from `state` instead of `native_value`, and `state_class` was put into the attributes rather than set on the entity. It reported correctly and even kept statistics that way, but none of it was the documented route, and the first change to Home Assistant's side of that would have broken it quietly.
- **`hacs.json` declares the Home Assistant version it needs**, `2024.7.0`. The config flow imports `section` from `homeassistant.data_entry_flow`, which arrived in that release; below it, the flow raises `ImportError` on load with nothing explaining why.
- The French translation was missing the "already configured" message the duplicate-name check raises, so a French-locale user typing a name twice was shown the raw key instead of a sentence. All three languages now carry the same set.
- A radar's speed value is escaped before it goes into the generated marker image. It is Lufop's own data going into markup, and the encoding that followed treated a `<` that arrived in the value and a `<` belonging to the image exactly alike.
- `LufopOptionsFlow` calls its parent's `__init__`, which is what sets the `_options` attribute the base class reads. Nothing asked for it yet, so nothing broke; the first line that did would have found an `AttributeError`.


## v2.1.2

### Fixed
- **An area with no radars in it looked like an outage.** Lufop answers “nothing in range” with a bare `null` rather than an empty list, and that was read as a broken response: the poll failed and every entity of that entry went unavailable, with `Lufop API returned an error: None` in the log. Route entries felt it worst – a route queries one narrow corridor per sample point, and most stretches of road legitimately hold no radar at all, so a single empty one failed the whole poll. An empty answer is now simply an empty result.
- **The narrowest corridor searched nothing at all.** A radius is converted into Lufop’s own search margin, one unit per 100m, and the result was rounded to the nearest whole unit. The smallest corridor width the form accepts, 50m, lands exactly on half a unit, which Python rounds to zero – so the tightest search anyone could ask for was the one that asked for no margin. Every other value rounded to nearest as well, meaning half of them quietly searched less ground than requested. The margin is now rounded up and never smaller than one unit.
- **A second area with the same name came up empty.** Every entity an entry creates is identified by that entry’s name, so two entries called the same thing produced identical identifiers and Home Assistant dropped the ones it could not tell apart – the new area appeared with no radars and no sensor, explained only by a line in the log. The name is now claimed when it is typed, so a duplicate is refused right there with “already configured” instead of failing quietly several screens later.
- **Every area logged under the same name.** Entries carried no identifier of their own, so each one’s coordinator wrote its messages as `lufop_radar (None)` and there was no telling which area a message came from. New entries use the name they were set up under; existing ones fall back to it.

## v2.1.0

### Added
- **`lufop_radar_new_radar` event**: fired once per radar that's genuinely new - never for one already known from an earlier poll, and never during the very first fetch right after Home Assistant starts (that's just "here's what's already there", not a new detection). Includes `config_entry_id`, `area`, `id`, `type`, `speed`, `street`, `city`, `country`, `latitude`, and `longitude`. Lets an automation react directly to a newly reported radar anywhere in the configured area/route, without needing a matching Home Assistant zone. See the README's new "Notify when a new radar is reported" section (event-based vs. zone-based approaches).

### Fixed
- **README images and License link not rendering in HACS**: every `<img>` and the License badge's link both used a repo-relative path (e.g. `docs/map-card-example.png`, `LICENSE`), which GitHub's own viewer resolves but HACS's README renderer does not. Switched to absolute `raw.githubusercontent.com`/`github.com` URLs.

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
