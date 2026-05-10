from shapely.geometry import Point, Polygon
from typing import List


def build_boundary(flat_coords: List[float]) -> Polygon:
    """
    Convert a flat [lat0, lon0, lat1, lon1, ...] list into a
    Shapely Polygon in (lon, lat) / (x, y) order.
    Raises ValueError if fewer than 3 coordinate pairs are provided.
    """
    if len(flat_coords) < 6 or len(flat_coords) % 2 != 0:
        raise ValueError('Need at least 3 (lat, lon) pairs.')
    return Polygon([
        (flat_coords[i + 1], flat_coords[i])
        for i in range(0, len(flat_coords), 2)
    ])


def is_inside(polygon: Polygon, lat: float, lon: float) -> bool:
    """Return True if (lat, lon) lies inside polygon."""
    return polygon.contains(Point(lon, lat))


def validate_coords(flat_coords: List[float]) -> bool:
    """Basic sanity check on coordinate ranges."""
    if len(flat_coords) % 2 != 0:
        return False
    for i in range(0, len(flat_coords), 2):
        lat, lon = flat_coords[i], flat_coords[i + 1]
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return False
    return True
