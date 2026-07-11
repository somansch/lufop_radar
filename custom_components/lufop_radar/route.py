from homeassistant.util import location as location_util


def route_sample_points(waypoints: list[dict], corridor_width: float) -> list[tuple[float, float]]:
    """Interpolate points along the waypoint chain, spaced corridor_width
    apart, so a circular query around each point overlaps its neighbours and
    leaves no gaps - a "poor man's route search" without a real routing
    engine. Straight lines between waypoints, not actual roads, so a route
    with sharp bends needs waypoints placed on those bends to stay accurate.

    Shared between the coordinator (to actually query each point) and the
    config flow (to suggest a default poll interval from the resulting
    point count), so the two stay in sync without duplicating the geometry.
    """
    points = [(waypoints[0]["latitude"], waypoints[0]["longitude"])]
    for start, end in zip(waypoints, waypoints[1:]):
        segment_length = location_util.distance(
            start["latitude"], start["longitude"], end["latitude"], end["longitude"]
        )
        steps = max(1, int(segment_length // corridor_width)) if segment_length else 1
        for step in range(1, steps + 1):
            fraction = step / steps
            points.append((
                start["latitude"] + (end["latitude"] - start["latitude"]) * fraction,
                start["longitude"] + (end["longitude"] - start["longitude"]) * fraction,
            ))
    return points
