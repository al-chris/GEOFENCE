#!/usr/bin/env python3
"""
Small utility to plot the geofence polygon and a circular fence.

Usage:
  python scripts/plot_geofence.py [--center-lat LAT] [--center-lon LON] [--radius M]

Creates `resource/geofence_plot.png` by default.
"""
from __future__ import annotations
import argparse
import math
import os
from typing import List, Tuple

import yaml
import numpy as np
import matplotlib.pyplot as plt


def load_boundary(path: str = "config/boundary.yaml") -> List[Tuple[float, float]]:
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
    coords = data.get("geofence_node", {}).get("ros__parameters", {}).get("boundary_coords", [])
    pts: List[Tuple[float, float]] = []
    for i in range(0, len(coords), 2):
        lat = float(coords[i])
        lon = float(coords[i + 1])
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
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"Saved plot to {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--center-lat", type=float, default=7.5185)
    parser.add_argument("--center-lon", type=float, default=4.5168)
    parser.add_argument("--radius", type=float, default=50.0, help="radius in metres")
    parser.add_argument("--out", default="resource/geofence_plot.png")
    parser.add_argument("--boundary", default="config/boundary.yaml")
    args = parser.parse_args()

    polygon = load_boundary(args.boundary)
    center = (args.center_lat, args.center_lon)
    plot(polygon, center, args.radius, args.out)


if __name__ == "__main__":
    main()
