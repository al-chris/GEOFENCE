#!/usr/bin/env python3
"""
Small utility to plot the geofence polygon and a circular fence.

Usage (from anywhere in the workspace):
  python scripts/plot_geofence.py [--center-lat LAT] [--center-lon LON] [--radius M]

Defaults are resolved relative to the package directory, not the current working
directory, so the script behaves the same whether it is run from the workspace
root or from `src/virtual_geofence`.

Creates `src/virtual_geofence/resource/geofence_plot.png` by default.
"""
from __future__ import annotations
import argparse
import math
import os
from typing import List, Tuple

import yaml
import numpy as np
import matplotlib.pyplot as plt

# Resolve the package directory from this script's location (scripts/ -> repo root).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pkg_path(*parts: str) -> str:
    """Resolve a file inside the package, preferring the colcon install tree."""
    candidates = [
        os.path.join(REPO_ROOT, "install", "virtual_geofence", "share", "virtual_geofence", *parts),
        os.path.join(REPO_ROOT, "src", "virtual_geofence", *parts),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[-1]


DEFAULT_BOUNDARY = _pkg_path("config", "boundary.yaml")
DEFAULT_OUT = _pkg_path("resource", "geofence_plot.png")


def load_boundary(path: str) -> List[Tuple[float, float]]:
    if not os.path.isfile(path):
        raise SystemExit(
            f"Boundary file not found: {path}\n"
            "Pass an explicit path with --boundary, e.g. "
            "--boundary src/virtual_geofence/config/boundary.yaml"
        )
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} does not contain a YAML mapping at the top level")

    node = data.get("geofence_node") or {}
    params = (node.get("ros__parameters") if isinstance(node, dict) else None) or {}
    coords = params.get("boundary_coords")

    if not coords:
        raise SystemExit(
            f"No 'geofence_node.ros__parameters.boundary_coords' list found in {path}"
        )
    if len(coords) % 2 != 0:
        raise SystemExit(
            f"boundary_coords in {path} must be a flat [lat, lon, lat, lon, ...] list; "
            f"got {len(coords)} values"
        )

    pts: List[Tuple[float, float]] = []
    for i in range(0, len(coords), 2):
        try:
            lat = float(coords[i])
            lon = float(coords[i + 1])
        except (TypeError, ValueError):
            raise SystemExit(
                f"boundary_coords in {path} must contain numbers; "
                f"got {coords[i]!r}, {coords[i + 1]!r}"
            )
        pts.append((lat, lon))
    return pts


def meters_per_degree(lat_deg: float) -> Tuple[float, float]:
    """Return approximate (meters_per_deg_lat, meters_per_deg_lon) at given latitude."""
    lat = math.radians(lat_deg)
    m_per_deg_lat = 111132.954 - 559.822 * math.cos(2 * lat) + 1.175 * math.cos(4 * lat)
    m_per_deg_lon = 111412.84 * math.cos(lat) - 93.5 * math.cos(3 * lat)
    return m_per_deg_lat, m_per_deg_lon


def point_segment_distance_m(point: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Shortest distance (m) from `point` to segment AB. Coordinates are (lat, lon)."""
    plat, plon = point
    lat0 = plat
    mlat, mlon = meters_per_degree(lat0)

    # convert to local meters with origin at point
    ax = (a[1] - plon) * mlon
    ay = (a[0] - plat) * mlat
    bx = (b[1] - plon) * mlon
    by = (b[0] - plat) * mlat

    # vector A and B relative to P (P at origin)
    # segment AB = B - A
    abx = bx - ax
    aby = by - ay

    # project origin onto AB: t = -A·AB / |AB|^2
    denom = abx * abx + aby * aby
    if denom == 0:
        # A and B are the same point
        return math.hypot(ax, ay)
    t = -(ax * abx + ay * aby) / denom
    t = max(0.0, min(1.0, t))
    cx = ax + t * abx
    cy = ay + t * aby
    return math.hypot(cx, cy)


def min_distance_to_polygon_m(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> float:
    if not polygon:
        return float("inf")
    n = len(polygon)
    min_d = float("inf")
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        d = point_segment_distance_m(point, a, b)
        if d < min_d:
            min_d = d
    return min_d


def polygon_centroid(polygon: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Area-weighted centroid (shoelace). Falls back to the vertex average if degenerate."""
    n = len(polygon)
    twice_area = 0.0
    x_sum = 0.0
    y_sum = 0.0
    for i in range(n):
        x0, y0 = polygon[i][1], polygon[i][0]          # (lon, lat)
        x1, y1 = polygon[(i + 1) % n][1], polygon[(i + 1) % n][0]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        x_sum += (x0 + x1) * cross
        y_sum += (y0 + y1) * cross
    if abs(twice_area) < 1e-18:
        return (sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n)
    area = twice_area * 0.5
    return (y_sum / (6 * area), x_sum / (6 * area))      # (lat, lon)


def polygon_size_m(polygon: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Approximate (width, height) of the polygon's bounding box in metres."""
    mlat, mlon = meters_per_degree(polygon[0][0])
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    return (max(lats) - min(lats)) * mlat, (max(lons) - min(lons)) * mlon


def make_circle_latlon(center: Tuple[float, float], radius_m: float, n: int = 128):
    lat0, lon0 = center
    mlat, mlon = meters_per_degree(lat0)
    angles = np.linspace(0, 2 * math.pi, n)
    dlat = (radius_m * np.sin(angles)) / mlat
    dlon = (radius_m * np.cos(angles)) / mlon
    lats = lat0 + dlat
    lons = lon0 + dlon
    return list(zip(lats.tolist(), lons.tolist()))


def plot(polygon: List[Tuple[float, float]], center: Tuple[float, float], radius_m: float, out_path: str):
    if not polygon:
        raise SystemExit("No polygon loaded")

    poly_lats = [p[0] for p in polygon] + [polygon[0][0]]
    poly_lons = [p[1] for p in polygon] + [polygon[0][1]]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.fill(poly_lons, poly_lats, alpha=0.25, fc="orange", ec="red", label="boundary")
    ax.plot(poly_lons, poly_lats, color="red")

    # circle (approximate in lat/lon)
    circ = make_circle_latlon(center, radius_m)
    circ_lats = [c[0] for c in circ]
    circ_lons = [c[1] for c in circ]
    ax.plot(circ_lons, circ_lats, color="blue", linestyle="--", label=f"circle {radius_m} m")

    ax.scatter([center[1]], [center[0]], color="blue", zorder=5)

    # compute min distance from center to polygon (m)
    min_d = min_distance_to_polygon_m(center, polygon)

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"Geofence: center {center[0]:.6f},{center[1]:.6f}  min-dist {min_d:.1f} m")
    ax.legend()
    ax.set_aspect("equal", adjustable="datalim")

    plt.tight_layout()
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"Saved plot to {out_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--center-lat",
        type=float,
        default=None,
        help="circle centre latitude (defaults to the boundary centroid)",
    )
    parser.add_argument(
        "--center-lon",
        type=float,
        default=None,
        help="circle centre longitude (defaults to the boundary centroid)",
    )
    parser.add_argument("--radius", type=float, default=50.0, help="radius in metres")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output image path")
    parser.add_argument("--boundary", default=DEFAULT_BOUNDARY, help="boundary YAML path")
    args = parser.parse_args()

    polygon = load_boundary(args.boundary)

    centroid = polygon_centroid(polygon)
    center = (
        centroid[0] if args.center_lat is None else args.center_lat,
        centroid[1] if args.center_lon is None else args.center_lon,
    )

    width_m, height_m = polygon_size_m(polygon)
    if args.radius > math.hypot(width_m, height_m) / 2:
        print(
            f"Note: the {args.radius:.1f} m circle is larger than the boundary "
            f"({width_m:.1f} x {height_m:.1f} m), so the plot will be dominated by the circle."
        )

    plot(polygon, center, args.radius, args.out)


if __name__ == "__main__":
    main()
