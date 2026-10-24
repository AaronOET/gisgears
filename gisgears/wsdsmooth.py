#!/usr/bin/env python
"""
wsdsmooth - Smooth the boundary of a watershed polygon shapefile.

Raster-derived watershed boundaries are jagged because they follow cell
edges. This tool replaces each boundary vertex with the average of the
`filter` vertices centred on it (wrapping around each closed ring, the same
moving-average approach as WhiteboxTools' smooth_vectors), keeping holes,
multipart polygons, attributes and the CRS. It works on the output of both
wsdgen and wsdpyshed and needs no external executable.
"""

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import MultiPolygon, Polygon


def _smooth_ring(coords, filter_size):
    """Moving-average a closed ring's vertices, wrapping around its ends."""
    pts = np.asarray(coords)[:-1, :2]  # drop the repeated closing vertex (and any Z)
    n = len(pts)
    # Keep the window no wider than the ring itself
    half = min(filter_size // 2, (n - 1) // 2)
    if half < 1:
        return coords
    padded = np.concatenate([pts[-half:], pts, pts[:half]])
    kernel = np.ones(2 * half + 1) / (2 * half + 1)
    smoothed = np.column_stack([
        np.convolve(padded[:, 0], kernel, mode="valid"),
        np.convolve(padded[:, 1], kernel, mode="valid"),
    ])
    return np.vstack([smoothed, smoothed[:1]])


def _smooth_polygon(poly, filter_size):
    smoothed = Polygon(
        _smooth_ring(poly.exterior.coords, filter_size),
        [_smooth_ring(ring.coords, filter_size) for ring in poly.interiors],
    )
    # Averaging can pull a narrow neck across itself; repair rather than
    # write an invalid polygon
    return smoothed if smoothed.is_valid else smoothed.buffer(0)


def _smooth_geometry(geom, filter_size):
    if geom is None or geom.is_empty:
        return geom
    if geom.geom_type == "Polygon":
        return _smooth_polygon(geom, filter_size)
    parts = []
    for part in geom.geoms:
        s = _smooth_polygon(part, filter_size)
        parts.extend(s.geoms if s.geom_type == "MultiPolygon" else [s])
    return MultiPolygon(parts)


def smooth_watershed(watershed, filter_size=9, outdir="WSD", output=None, cwd=None) -> Path:
    """
    Smooth the boundary of a watershed polygon shapefile.

    Args:
        watershed (str): Path to the input watershed polygon shapefile
        filter_size (int): Smoothing filter size, the number of vertices
            averaged per output vertex (odd, >=3, default 9); larger values
            produce smoother boundaries
        outdir (str): Output folder name (default: WSD)
        output (str): Output file name inside outdir (default:
            <input name>_smooth.shp)
        cwd (Path): Working directory to resolve relative paths against
            (defaults to the current directory)

    Returns:
        Path: Path of the smoothed shapefile
    """
    if filter_size < 3 or filter_size % 2 == 0:
        sys.exit(f"Error: filter size must be an odd number >= 3, got {filter_size}")

    cwd = Path(cwd) if cwd is not None else Path.cwd()
    in_path = Path(watershed)
    in_path = in_path if in_path.is_absolute() else cwd / in_path
    if not in_path.is_file():
        sys.exit(f"Error: required input file not found: {in_path}")

    gdf = gpd.read_file(in_path)
    if gdf.empty:
        sys.exit(f"Error: watershed layer has no features: {in_path}")
    if not gdf.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        sys.exit(f"Error: watershed layer must be a polygon layer: {in_path}")

    output_dir = cwd / outdir
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / (output or f"{in_path.stem}_smooth.shp")
    if out_path.resolve() == in_path.resolve():
        sys.exit(f"Error: output would overwrite the input: {out_path}")

    vertices_before = gdf.count_coordinates().sum()
    gdf["geometry"] = gdf.geometry.apply(lambda g: _smooth_geometry(g, filter_size))
    gdf.to_file(out_path)

    print(f"Smoothed {len(gdf)} feature(s), {vertices_before} vertices, filter size {filter_size}")
    print(f"Wrote {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        prog="wsdsmooth",
        description="Smooth the boundary of a watershed polygon shapefile",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  wsdsmooth WSD/watershed.shp                      # -> WSD/watershed_smooth.shp
  wsdsmooth watershed.shp --filter 15              # Smoother boundary
  wsdsmooth watershed.shp -o basin_smooth.shp --outdir Out
        """,
    )
    parser.add_argument("watershed", help="Input watershed polygon shapefile path")
    parser.add_argument(
        "--filter",
        type=int,
        default=9,
        help="Smoothing filter size (odd number, >=3, default 9); "
             "larger values produce smoother boundaries",
    )
    parser.add_argument("--outdir", default="WSD", help="Output folder name (default: WSD)")
    parser.add_argument(
        "-o", "--output",
        help="Output file name inside --outdir (default: <input name>_smooth.shp)",
    )
    args = parser.parse_args()

    smooth_watershed(
        watershed=args.watershed,
        filter_size=args.filter,
        outdir=args.outdir,
        output=args.output,
    )


if __name__ == "__main__":
    main()
