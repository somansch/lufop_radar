from math import ceil, cos, hypot, radians

from homeassistant.util import location as location_util

# Lufop's search margin is a whole number of 100 m steps (see
# LufopAPI.get_radars), so that is the smallest circle a request can ask for.
_MARGIN_STEP = 100


def search_radius(corridor_width: float) -> float:
    """The radius a request for this corridor width really searches."""
    return max(1, ceil(corridor_width / _MARGIN_STEP)) * _MARGIN_STEP


def route_sample_points(waypoints: list[dict], corridor_width: float) -> list[tuple[float, float]]:
    """Interpolate points along the waypoint chain so that a circular query
    around each point overlaps its neighbours and leaves no gaps - a "poor
    man's route search" without a real routing engine. Straight lines between
    waypoints, not actual roads, so a route with sharp bends needs waypoints
    placed on those bends to stay accurate.

    Spaced by the radius a request really searches, not by the corridor
    width as typed: a 50 m corridor is asked for with Lufop's smallest
    margin, 100 m, and points every 50 m were twice the requests for the
    same ground. What lies outside the corridor is dropped afterwards (see
    distance_to_route).

    Shared between the coordinator (to actually query each point) and the
    config flow (to suggest a default poll interval from the resulting
    point count), so the two stay in sync without duplicating the geometry.
    """
    spacing = search_radius(corridor_width)
    points = [(waypoints[0]["latitude"], waypoints[0]["longitude"])]
    for start, end in zip(waypoints, waypoints[1:]):
        segment_length = location_util.distance(
            start["latitude"], start["longitude"], end["latitude"], end["longitude"]
        )
        if not segment_length:
            # The same point twice adds nothing to ask for.
            continue
        steps = max(1, int(segment_length // spacing))
        for step in range(1, steps + 1):
            fraction = step / steps
            points.append((
                start["latitude"] + (end["latitude"] - start["latitude"]) * fraction,
                start["longitude"] + (end["longitude"] - start["longitude"]) * fraction,
            ))
    return points


def distance_to_route(waypoints: list[dict], lat: float, lng: float) -> float:
    """Metres from a point to the nearest stretch of the waypoint chain.

    On a flat map around the point itself, which over the few hundred metres
    a corridor is wide is exact enough.
    """
    metres_per_degree_lat = 111_320.0
    metres_per_degree_lng = metres_per_degree_lat * cos(radians(lat))

    def flat(point: dict) -> tuple[float, float]:
        return (
            (point["longitude"] - lng) * metres_per_degree_lng,
            (point["latitude"] - lat) * metres_per_degree_lat,
        )

    if len(waypoints) == 1:
        return hypot(*flat(waypoints[0]))

    best = float("inf")
    for start, end in zip(waypoints, waypoints[1:]):
        ax, ay = flat(start)
        bx, by = flat(end)
        dx, dy = bx - ax, by - ay
        length_squared = dx * dx + dy * dy
        # Where on the stretch the point's perpendicular lands, held to
        # the stretch's two ends.
        t = 0.0 if not length_squared else max(
            0.0, min(1.0, -(ax * dx + ay * dy) / length_squared)
        )
        best = min(best, hypot(ax + t * dx, ay + t * dy))
    return best
