#!/usr/bin/env python
"""
showtif - Display a DEM GeoTIFF with an elevation colormap and hillshade.

Prints the raster's CRS, size, cell size, nodata value and elevation
statistics, then plots the elevation and a hillshade side by side.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource
from pyproj import CRS


def load_dem(path):
    """Read band 1 of a DEM as a masked float array, plus its extent and metadata."""
    with rasterio.open(path) as src:
        dem = src.read(1, masked=True).astype("float64")
        # Treat common sentinel values as nodata when the file doesn't declare one
        if src.nodata is None:
            dem = np.ma.masked_where(dem <= -999, dem)
        b = src.bounds
        extent = (b.left, b.right, b.bottom, b.top)
        info = {
            "crs": src.crs,
            "shape": src.shape,
            "res": src.res,
            "nodata": src.nodata,
        }
    return dem, extent, info


def describe_crs(crs):
    """Return a one-line projection summary and the axis unit for the plot."""
    if crs is None:
        return "Projection: unknown (no CRS)", "?"
    pcrs = CRS.from_user_input(crs.to_wkt())
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


def show_dem(path, show=True):
    """Print DEM info and plot its elevation and hillshade. Returns the figure."""
    dem, extent, info = load_dem(path)

    print(f"File   : {path}")
    print(f"CRS    : {info['crs']}")
    print(f"Size   : {info['shape'][1]} cols x {info['shape'][0]} rows")
    print(f"Cell   : {info['res'][0]} x {info['res'][1]}")
    print(f"NoData : {info['nodata']}")
    print(f"Elev   : min={dem.min():.2f}  max={dem.max():.2f}  mean={dem.mean():.2f}")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)

    im = ax1.imshow(dem, cmap="terrain", extent=extent, interpolation="nearest")
    ax1.set_title("Elevation")
    fig.colorbar(im, ax=ax1, label="Elevation (m)", shrink=0.8)

    ls = LightSource(azdeg=315, altdeg=45)
    filled = dem.filled(np.nan if dem.count() == 0 else dem.min())
    shaded = ls.shade(filled, cmap=plt.get_cmap("terrain"), blend_mode="overlay",
                      vert_exag=1, dx=info["res"][0], dy=info["res"][1])
    shaded[np.ma.getmaskarray(dem)] = (1, 1, 1, 1)
    ax2.imshow(shaded, extent=extent, interpolation="nearest")
    ax2.set_title("Hillshade")

    proj_text, unit = describe_crs(info["crs"])
    for ax in (ax1, ax2):
        ax.set_xlabel(f"Easting ({unit})")
        ax.set_ylabel(f"Northing ({unit})")
        ax.ticklabel_format(useOffset=False, style="plain")

    fig.suptitle(f"{Path(path).name}\n{proj_text}")
    if show:
        plt.show()
    return fig


def main():
    parser = argparse.ArgumentParser(
        prog="showtif",
        description="Display a DEM GeoTIFF as an elevation map and a hillshade, "
                    "and print its CRS, size, cell size, nodata and elevation stats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  showtif dem.tif
        """,
    )
    parser.add_argument("tif", type=Path, help="Path to the DEM .tif file")
    args = parser.parse_args()

    if not args.tif.exists():
        raise SystemExit(f"File not found: {args.tif}")
    show_dem(args.tif)


if __name__ == "__main__":
    main()
