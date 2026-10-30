#!/usr/bin/env python
"""
showtif2 - Display a DEM GeoTIFF with an elevation colormap and hillshade,
using terrio (pure Rust, no GDAL) instead of rasterio.

Prints the raster's CRS, size, cell size, nodata value and elevation
statistics, then plots the elevation and a hillshade side by side. The
hillshade is computed by terrio.dem, which matches gdaldem pixel for pixel.
"""

import argparse
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from pyproj import CRS


def _terrio():
    # Imported on use so the rest of gisgears still loads without terrio
    try:
        import terrio
    except ImportError:
        raise SystemExit("showtif2 requires terrio: pip install terrio")
    return terrio


def load_dem(path):
    """
    Read band 1 of a DEM with terrio as a masked float array, plus its
    extent, metadata and the terrio Raster itself (for terrain analysis).
    """
    terrio = _terrio()
    src = terrio.open_raster(str(path))
    dem = src.read(1).astype("float64")

    mask = np.zeros(dem.shape, dtype=bool)
    if src.nodata is not None:
        mask |= dem == src.nodata
    else:
        # Treat common sentinel values as nodata when the file doesn't declare one
        mask |= dem <= -999
    if src.has_mask:
        mask |= src.read_mask() == 0
    mask |= np.isnan(dem)
    dem = np.ma.masked_array(dem, mask=mask)

    left, bottom, right, top = src.bounds
    extent = (left, right, bottom, top)
    info = {
        "crs": src.crs,
        "shape": (src.height, src.width),
        "res": src.res,
        "nodata": src.nodata,
    }
    return dem, extent, info, src


def _resolve_crs(crs):
    """
    terrio returns the CRS as WKT, often named "unknown"; look it up by its
    authority code (e.g. ESRI:102043) when pyproj can identify it, so the
    CRS gets its proper name. Returns (pyproj CRS, short label).
    """
    if crs is None:
        return None, None
    pcrs = CRS.from_user_input(crs)
    authority = pcrs.to_authority()
    if authority:
        code = ":".join(authority)
        return CRS.from_user_input(code), code
    return pcrs, pcrs.name


def describe_crs(pcrs):
    """Return a one-line projection summary and the axis unit for the plot."""
    if pcrs is None:
        return "Projection: unknown (no CRS)", "?"
    parts = [pcrs.name]
    epsg = pcrs.to_epsg()
    if epsg:
        parts.append(f"EPSG:{epsg}")
    if pcrs.coordinate_operation:
        parts.append(pcrs.coordinate_operation.method_name)
    if pcrs.datum:
        parts.append(f"Datum: {pcrs.datum.name}")
    unit = pcrs.axis_info[0].unit_name if pcrs.axis_info else "?"
    unit = {"metre": "m", "degree": "°"}.get(unit, unit)
    return "  |  ".join(parts), unit


def show_dem(path, show=True, hillshade=False, azdeg=315, altdeg=45):
    """
    Print DEM info and plot its elevation; with hillshade=True, also plot a
    hillshade alongside, lit from azimuth azdeg and altitude altdeg (degrees).
    Returns the figure.
    """
    terrio = _terrio()
    dem, extent, info, src = load_dem(path)
    crs, crs_label = _resolve_crs(info["crs"])

    print(f"File   : {path}")
    print(f"CRS    : {crs_label}")
    print(f"Size   : {info['shape'][1]} cols x {info['shape'][0]} rows")
    print(f"Cell   : {info['res'][0]} x {info['res'][1]}")
    print(f"NoData : {info['nodata']}")
    print(f"Elev   : min={dem.min():.2f}  max={dem.max():.2f}  mean={dem.mean():.2f}")

    if hillshade:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
        axes = (ax1, ax2)
    else:
        fig, ax1 = plt.subplots(figsize=(8, 6), constrained_layout=True)
        axes = (ax1,)

    im = ax1.imshow(dem, cmap="terrain", extent=extent, interpolation="nearest")
    ax1.set_title("Elevation")
    fig.colorbar(im, ax=ax1, label="Elevation (m)", shrink=0.8)

    if hillshade:
        # gdaldem-style hillshade (default azimuth 315, altitude 45), with the elevation
        # colormap laid over it; nodata stays blank
        shade = terrio.dem(src, "hillshade", azimuth=azdeg, altitude=altdeg)
        hs = np.ma.masked_array(shade.read(1), mask=np.ma.getmaskarray(dem))
        ax2.imshow(hs, cmap="gray", extent=extent, interpolation="nearest")
        ax2.imshow(dem, cmap="terrain", alpha=0.45, extent=extent, interpolation="nearest")
        ax2.set_title(f"Hillshade (azimuth {azdeg:g}°, altitude {altdeg:g}°)")

    proj_text, unit = describe_crs(crs)
    for ax in axes:
        ax.set_xlabel(f"Easting ({unit})")
        ax.set_ylabel(f"Northing ({unit})")
        ax.ticklabel_format(useOffset=False, style="plain")

    # Wrap the projection line so it fits the narrower elevation-only figure
    proj_text = textwrap.fill(proj_text, width=140 if hillshade else 85)
    fig.suptitle(f"{Path(path).name}\n{proj_text}")
    if show:
        plt.show()
    return fig


def main():
    parser = argparse.ArgumentParser(
        prog="showtif2",
        description="Display a DEM GeoTIFF as an elevation map (optionally with a hillshade) "
                    "using terrio (no GDAL), and print its CRS, size, cell size, nodata and "
                    "elevation stats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  showtif2 dem.tif                # Elevation only
  showtif2 dem.tif -H             # Elevation and hillshade side by side
  showtif2 dem.tif -H --azdeg 270 --altdeg 30   # Light from the west, lower sun
        """,
    )
    parser.add_argument("tif", type=Path, help="Path to the DEM .tif file")
    parser.add_argument("-H", "--hillshade", action="store_true",
                        help="Also plot a hillshade next to the elevation map")
    parser.add_argument("--azdeg", type=float, default=315,
                        help="Hillshade light azimuth in degrees, clockwise from north (default: 315)")
    parser.add_argument("--altdeg", type=float, default=45,
                        help="Hillshade light altitude in degrees above the horizon (default: 45)")
    args = parser.parse_args()

    if not args.tif.exists():
        raise SystemExit(f"File not found: {args.tif}")
    show_dem(args.tif, hillshade=args.hillshade, azdeg=args.azdeg, altdeg=args.altdeg)


if __name__ == "__main__":
    main()
