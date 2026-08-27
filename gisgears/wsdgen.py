#!/usr/bin/env python
"""
wsdgen - Delineate a watershed from a DEM and an outlet layer (point or line).

Given a DEM raster and an outlet (pour point) shapefile - which may be a
point layer (a single manually-marked outlet) or a line layer (e.g. a
cross-section at the watershed outlet) - this tool breaches depressions,
computes D8 flow direction/accumulation, snaps the outlet onto the stream,
delineates the watershed, and converts the result to polygon shapefiles
(raw and boundary-smoothed).

Requires the WhiteboxTools executable, which the `whitebox` Python package
downloads automatically on first use.
"""

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import rasterio
import shapefile
from whitebox import WhiteboxTools


def _snap_raster_pour_points(outlet_raster_path, flow_accum_path, output_path, snap_dist):
    """
    Relocate each labeled outlet cell to the highest-flow-accumulation cell
    within snap_dist, the same way WhiteboxTools' snap_pour_points does for
    point outlets.
    """
    with rasterio.open(outlet_raster_path) as src:
        outlet = src.read(1)
        profile = src.profile
        outlet_nodata = src.nodata
        cellsize = abs(src.transform.a)

    with rasterio.open(flow_accum_path) as src:
        flow_accum = src.read(1)
        fa_nodata = src.nodata

    radius_cells = max(1, round(snap_dist / cellsize))
    rows, cols = outlet.shape
    snapped = np.full_like(outlet, outlet_nodata)

    ids = np.unique(outlet)
    ids = ids[ids != outlet_nodata]

    for outlet_id in ids:
        ys, xs = np.where(outlet == outlet_id)
        # Start the search from whichever of this outlet's cells is already
        # closest to the channel, then look for the true peak nearby
        seed_r, seed_c = ys[np.argmax(flow_accum[ys, xs])], xs[np.argmax(flow_accum[ys, xs])]

        r0, r1 = max(0, seed_r - radius_cells), min(rows, seed_r + radius_cells + 1)
        c0, c1 = max(0, seed_c - radius_cells), min(cols, seed_c + radius_cells + 1)
        window = flow_accum[r0:r1, c0:c1]

        valid = window != fa_nodata if fa_nodata is not None else np.ones_like(window, dtype=bool)
        if valid.any():
            masked = np.where(valid, window, -np.inf)
            local_r, local_c = np.unravel_index(np.argmax(masked), masked.shape)
            snap_r, snap_c = r0 + local_r, c0 + local_c
        else:
            snap_r, snap_c = seed_r, seed_c

        snapped[snap_r, snap_c] = outlet_id

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(snapped, 1)


def delineate_watershed(dem, outlet, outdir="WSD", all_outputs=False, smooth_filter=9, cwd=None) -> Path:
    """
    Delineate a watershed from a DEM and an outlet layer (point or line).

    Args:
        dem (str): Path to the input DEM raster
        outlet (str): Path to the outlet (pour point) shapefile - point or line
        outdir (str): Output folder name (default: WSD)
        all_outputs (bool): Keep intermediate files (breach/pointer/flow
            accumulation/snapped outlet, etc.) in outdir instead of a temp
            folder that is deleted after processing
        smooth_filter (int): Boundary smoothing filter size (odd, >=3)
        cwd (Path): Working directory to resolve relative paths against and
            to run WhiteboxTools from (defaults to the current directory)

    Returns:
        Path: Output directory containing watershed.tif, watershed.shp and
            watershed_smooth.shp
    """
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    dem_path = Path(dem)
    dem_path = dem_path if dem_path.is_absolute() else cwd / dem_path
    outlet_path = Path(outlet)
    outlet_path = outlet_path if outlet_path.is_absolute() else cwd / outlet_path

    for p in (dem_path, outlet_path):
        if not p.is_file():
            sys.exit(f"Error: required input file not found: {p}")

    wbt = WhiteboxTools()
    wbt.set_working_dir(str(cwd))

    # whitebox_tools.exe cannot correctly resolve relative paths to subfolders
    # on Windows, so input and output files always use absolute paths
    dem_str = str(dem_path.resolve())
    outlet_str = str(outlet_path.resolve())

    output_dir = cwd / outdir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Intermediate files are written to a temp folder by default and deleted
    # entirely after processing; pass all_outputs=True to keep them in
    # output_dir for inspection
    if all_outputs:
        inter_dir = output_dir
        tmp_dir = None
    else:
        tmp_dir = tempfile.TemporaryDirectory()
        inter_dir = Path(tmp_dir.name)

    dem_breached = str(inter_dir / "dem_breached.tif")
    d8_pointer = str(inter_dir / "d8_pointer.tif")
    flow_accum = str(inter_dir / "flow_accum.tif")
    outlet_snapped = str(inter_dir / "outlet_snapped.shp")
    outlet_raster = str(inter_dir / "outlet_raster.tif")
    outlet_raster_snapped = str(inter_dir / "outlet_raster_snapped.tif")
    watershed_out = str(output_dir / "watershed.tif")
    watershed_vector = str(output_dir / "watershed.shp")
    watershed_vector_smooth = str(output_dir / "watershed_smooth.shp")

    try:
        with rasterio.open(dem_str) as src:
            gridsize = abs(src.transform.a)

        wbt.breach_depressions(dem_str, dem_breached)
        wbt.d8_pointer(dem_breached, d8_pointer)
        wbt.d8_flow_accumulation(
            d8_pointer,
            flow_accum,
            out_type="cells",
            pntr=True,
        )

        # The outlet layer may be a point (single outlet) or a line (e.g. a
        # cross-section at the watershed outlet); the geometry type of the
        # shapefile determines the workflow
        with shapefile.Reader(outlet_str) as sf:
            is_point_outlet = sf.shapeType in (
                shapefile.POINT, shapefile.POINTZ, shapefile.POINTM
            )

        if is_point_outlet:
            # The outlet point is manually marked and not yet snapped to the
            # stream, so snap it using the flow accumulation grid first;
            # snap_dist is set to 3x the DEM cell resolution to capture
            # nearby cells
            wbt.snap_pour_points(
                outlet_str,
                flow_accum,
                outlet_snapped,
                snap_dist=3 * gridsize,
            )
            pour_points = outlet_snapped
        else:
            # A line cannot be snapped to the stream with snap_pour_points
            # (which only accepts point layers), so rasterize the line into
            # outlet cells first, then snap each rasterized outlet cell onto
            # the nearest high-flow-accumulation cell within snap_dist -
            # without this, a line that is even one pixel off the true
            # channel yields a near-empty watershed
            wbt.vector_lines_to_raster(
                outlet_str,
                outlet_raster,
                field="FID",
                base=flow_accum,
            )
            _snap_raster_pour_points(
                outlet_raster,
                flow_accum,
                outlet_raster_snapped,
                snap_dist=3 * gridsize,
            )
            pour_points = outlet_raster_snapped

        wbt.watershed(
            d8_pointer,
            pour_points,
            watershed_out,
        )

        # Convert the watershed raster output to a polygon shapefile for
        # easier viewing in GIS and further analysis
        wbt.raster_to_vector_polygons(
            watershed_out,
            watershed_vector,
        )

        # Raster-to-polygon boundaries are jagged (following cell edges), so
        # also output a smoothed version for downstream use/presentation
        wbt.smooth_vectors(
            watershed_vector,
            watershed_vector_smooth,
            filter=smooth_filter,
        )
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()

    print(f"Wrote watershed.tif, watershed.shp, watershed_smooth.shp to {output_dir}")
    return output_dir


def main():
    parser = argparse.ArgumentParser(
        prog="wsdgen",
        description="Extract a watershed from a DEM and an outlet layer (point or line)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  wsdgen --dem dem.tif --outlet outlet.shp                       # Point outlet
  wsdgen --dem dem.tif --outlet crosssection.shp --all-outputs   # Keep intermediates
        """,
    )
    parser.add_argument("--dem", required=True, help="Input DEM file path")
    parser.add_argument(
        "--outlet",
        required=True,
        help="Outlet (pour point) shapefile path, can be a point or line layer",
    )
    parser.add_argument("--outdir", default="WSD", help="Output folder name (default: WSD)")
    parser.add_argument(
        "--all-outputs",
        action="store_true",
        help="Keep all intermediate files (breach/pointer/flow accumulation/snapped outlet, etc.); "
             "by default only the final watershed.tif and watershed.shp are output",
    )
    parser.add_argument(
        "--smooth-filter",
        type=int,
        default=9,
        help="Boundary smoothing filter size (odd number, >=3, default 9); "
             "larger values produce smoother boundaries; output is watershed_smooth.shp",
    )
    args = parser.parse_args()

    delineate_watershed(
        dem=args.dem,
        outlet=args.outlet,
        outdir=args.outdir,
        all_outputs=args.all_outputs,
        smooth_filter=args.smooth_filter,
    )


if __name__ == "__main__":
    main()
