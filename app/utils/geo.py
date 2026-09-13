"""
Deterministic geospatial calculations.

IMPORTANT (architecture rule): distance / geofence calculations must NEVER be
delegated to the LLM/agent. This module is the single source of truth for
GPS math used across the application.
"""
import math

EARTH_RADIUS_METERS = 6371000.0


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two lat/lon points, in meters."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_METERS * c


def is_inside_geofence(
    lat: float, lon: float, place_lat: float, place_lon: float, radius_meters: float
) -> tuple[bool, float]:
    """Return (inside, distance_meters) for a point relative to a circular geofence."""
    distance = haversine_distance_meters(lat, lon, place_lat, place_lon)
    return distance <= radius_meters, distance


def is_valid_latitude(lat: float) -> bool:
    return -90.0 <= lat <= 90.0


def is_valid_longitude(lon: float) -> bool:
    return -180.0 <= lon <= 180.0
