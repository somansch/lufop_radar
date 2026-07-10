# Lufop Radar Integration for Home Assistant 📡

[![GitHub release](https://img.shields.io/github/v/release/somansch/lufop_radar)](https://github.com/somansch/lufop_radar/releases/latest)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/somansch/lufop_radar)](LICENSE)

## Overview

This Home Assistant custom integration reports speed cameras, mobile radar checks, construction-zone controls, and red light cameras near a configured location, using the [Lufop](https://lufop.net) radar database — a free, officially documented API covering 20+ countries. Unlike some other radar data sources, Lufop's API is meant to be used by third-party developers: it just requires a free, personal API key.

Each detected radar is exposed as a `geo_location` entity, so it shows up natively on the [map card](https://www.home-assistant.io/dashboards/map/), and a running total is exposed as a sensor.

## Getting an API key

Lufop requires a personal API key before you can use the integration:

1. Go to [api.lufop.net](https://api.lufop.net/#apiAccessForm) and fill out the request form (country, name, email, organization, project description, intended use).
2. Once approved, you'll receive your key and access to a usage dashboard.
3. Enter that key in the config flow below.

## Installation

### HACS (recommended)

1. Install HACS if you don't have it already
2. Open HACS in Home Assistant
3. Go to any of the sections (integrations, frontend, automation)
4. Click on the 3 dots in the top right corner
5. Select "Custom repositories"
6. Add the following URL to the repository: `https://github.com/somansch/lufop_radar`
7. Select "Integration" as category
8. Click the "ADD" button
9. Search for "Lufop Radar"
10. Click the "Download" button

### Manual

Download `lufop_radar.zip` from the [latest release](https://github.com/somansch/lufop_radar/releases/latest) and extract its contents to the `config/custom_components/lufop_radar` directory:

```bash
mkdir -p custom_components/lufop_radar
cd custom_components/lufop_radar
wget https://github.com/somansch/lufop_radar/releases/latest/download/lufop_radar.zip
unzip lufop_radar.zip
rm lufop_radar.zip
```

## Configuration

### Adding an area

From the Home Assistant front page, go to **Settings** and then select **Devices & Services** from the list. Use the **Add Integration** button in the bottom right, search for "Lufop Radar" and add your first area. The integration itself is only added once — to track additional areas, open the already-added "Lufop Radar" integration card and use its own **Add entry** option to create another entry, one per area, each with its own entities.

| Field | Description |
|---|---|
| **Display name / Anzeigename** | Freely chosen name for this area. Used as a suffix in entity names and IDs, and as the `area` attribute on every `geo_location` entity it creates. |
| **API key / API-Schlüssel** | Your personal Lufop API key (see [Getting an API key](#getting-an-api-key)). |
| **Country / Land** | The country to query (Lufop scopes each request to a single country on the free plan). |
| **Section / Bereich** | Drag the map to the center point you want to monitor and adjust the radius circle. All radars within this radius are reported. |
| **Types** – Fixed / Fest | Include permanently installed fixed speed cameras. |
| **Types** – Mobile / Mobil | Include mobile radar checks. |
| **Types** – Construction zone / Baustelle | Include construction-zone speed controls. |
| **Types** – Red light / Rotlichtampel | Include red light cameras. |
| **Optional settings / Optionale Einstellungen** – Number of sensors / Anzahl der Sensoren | Upper limit on how many radars are tracked at once (default 9). |
| **Optional settings / Optionale Einstellungen** – Whitelist (regex filter of city names) / Whitelist (Regex Filter der Städtenamen) | Only radars whose city matches this regex are kept (default `.*`, i.e. no filtering). |
| **Optional settings / Optionale Einstellungen** – Blacklist | Comma-separated list of radar IDs to always exclude, regardless of the whitelist regex. |

Every field above can be changed afterwards: go to **Settings → Devices & Services**, find the entry for the area you want to change, and click **Configure**.

### Created entities

Each area produces the following entities:

| Entity | Description |
|---|---|
| Total count sensor (`sensor.*`) | Number of currently reported radars in this area (capped at "Number of sensors"). Its attributes break the count down per city. |
| One `geo_location` entity per radar (`geo_location.*`) | Created and removed dynamically as radars appear and disappear from the live data — there's no fixed pool of entities. |

Attributes on each radar's `geo_location` entity:

| Attribute | Description |
|---|---|
| `state` | Distance from the area's center point, in km (or miles, depending on your unit system). |
| `source` | `lufop_radar_<area>`, e.g. `lufop_radar_berlin`. Lets a map card select one specific area via `geo_location_sources`. |
| `area` | The display name you gave this area. |
| `type` | One of `fixe`, `mobile`, `chantier`, or `feu` (Lufop's own vocabulary). |
| `id` | The radar's Lufop ID, also usable for the blacklist option. |
| `vitesse` | Speed limit at this location. |
| `city`, `street` | Address of the radar (`commune`/`voie` in Lufop's data). |
| `country` | Country code as reported by Lufop. |
| `flash_direction` | Flash direction (`F`/`B`/`D`). |
| `azimut` | Compass bearing (0-360). |
| `updated` | Last update timestamp from Lufop. |

## Help and Contribution

If you find a problem, feel free to open an issue and I will do my best to help. If you have something to contribute, your help is greatly appreciated! If you want to add a new feature, please open a pull request first so we can discuss the details.

## Disclaimer

This custom integration is not officially affiliated with Lufop. Data is provided by [Lufop](https://lufop.net) under a [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) license, which permits commercial use with attribution. Unlike some other radar data sources, Lufop's API is an intentional, documented developer offering rather than a reverse-engineered endpoint — but you still need your own API key, and should review [Lufop's terms](https://api.lufop.net/) for your specific use case.
