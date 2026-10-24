#!/usr/bin/env python
"""
wsdpyshed - Delineate a watershed from a DEM and an outlet (point or line) using pysheds.

A pure-Python alternative to wsdgen (no WhiteboxTools executable needed).
Given a DEM raster and an outlet - a point or line shapefile, or x/y
coordinates in the DEM's CRS - this tool conditions the DEM (fills pits and
depressions, resolves flats), computes D8 flow direction and accumulation,
snaps a point outlet onto the nearest cell whose accumulation exceeds the
threshold, delineates the catchment, and extracts the stream network inside
it. A line outlet (e.g. a cross-section at the watershed outlet) is
rasterized, and the catchment is the union of everything draining to any
cell the line crosses.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

# pysheds 0.5 still calls np.in1d, which was removed in NumPy 2.4
if not hasattr(np, "in1d"):
    np.in1d = np.isin

import geopandas as gpd
from pysheds.grid import Grid
from pysheds.sview import Raster
from rasterio.features import rasterize
from shapely.geometry import Point, shape

# D8 direction codes, ordered N, NE, E, SE, S, SW, W, NW (ESRI convention)
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)


def _resolve(path, cwd):
    path = Path(path)
    return path if path.is_absolute() else cwd / path


def _read_outlet(outlet_path, dem_crs, index):
    """Return feature `index` of a point or line layer as a geometry in the DEM's CRS."""
    features = gpd.read_file(outlet_path)
    if features.empty:
        sys.exit(f"Error: outlet layer has no features: {outlet_path}")
    if not features.geom_type.isin(["Point", "MultiPoint", "LineString", "MultiLineString"]).all():
        sys.exit(f"Error: outlet layer must be a point or line layer: {outlet_path}")
    if not 0 <= index < len(features):
        sys.exit(f"Error: outlet index {index} out of range (layer has {len(features)} features)")
    if len(features) > 1:
        print(f"Outlet layer has {len(features)} features; using feature {index}")

    if features.crs is not None:
        features = features.to_crs(dem_crs.srs)
    else:
        print("Warning: outlet layer has no CRS; assuming it matches the DEM")

    geom = features.geometry.iloc[index]
    if geom.geom_type == "MultiPoint":
        geom = geom.geoms[0]
    return geom


def _cell_center(grid, row, col):
    return grid.affine * (col + 0.5, row + 0.5)


def _line_catchment(grid, fdir, acc, line_mask):
    """
    Union of the catchments of every cell in line_mask. Cells are visited in
    descending accumulation order, and a cell already inside the union is
    skipped because its own catchment is contained in it - so a cross-section
    over one channel usually needs a single catchment call.
    """
    rows, cols = np.nonzero(line_mask)
    order = np.argsort(np.asarray(acc)[rows, cols])[::-1]
    union = np.zeros(grid.shape, dtype=bool)
    first = None
    for r, c in zip(rows[order], cols[order]):
        if union[r, c]:
            continue
        catch = grid.catchment(x=c, y=r, fdir=fdir, dirmap=DIRMAP, xytype="index")
        first = catch if first is None else first
        union |= np.asarray(catch, dtype=bool)
    return Raster(union, viewfinder=first.viewfinder)


def delineate_watershed(dem, outlet=None, xy=None, outdir="WSD", acc_threshold=200,
                        outlet_index=0, no_snap=False, all_outputs=False,
                        web_map=False, plot=False, cwd=None) -> Path:
    """
    Delineate a watershed from a DEM and an outlet (point or line) using pysheds.

    Args:
        dem (str): Path to the input DEM raster
        outlet (str): Path to a point or line shapefile holding the outlet;
            reprojected to the DEM's CRS if needed. A line (e.g. a
            cross-section) yields the catchment draining to any cell it
            crosses. Ignored when xy is given
        xy (tuple): Pour point (x, y) in the DEM's CRS, instead of outlet
        outdir (str): Output folder name (default: WSD)
        acc_threshold (int): Flow accumulation (cell count) above which a cell
            is treated as a stream; used both to snap the pour point and to
            extract the stream network (default: 200)
        outlet_index (int): Which feature of the outlet layer to use (default: 0)
        no_snap (bool): Use the pour point as-is instead of snapping it to
            the nearest stream cell (a line outlet is only snapped when no
            cell it crosses exceeds acc_threshold)
        all_outputs (bool): Also write the conditioned DEM, flow direction
            and flow accumulation rasters (full DEM extent)
        web_map (bool): Also write an interactive streams_map.html
            (requires folium and mapclassify)
        plot (bool): Show the DEM, catchment and stream network in matplotlib
        cwd (Path): Working directory to resolve relative paths against
            (defaults to the current directory)

    Returns:
        Path: Output directory containing watershed.tif, watershed.shp,
            dem_clipped.tif, streams.gpkg and streams.geojson
    """
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    dem_path = _resolve(dem, cwd)
    if not dem_path.is_file():
        sys.exit(f"Error: required input file not found: {dem_path}")
    if xy is None:
        if outlet is None:
            sys.exit("Error: give either an outlet shapefile or x/y pour point coordinates")
        outlet_path = _resolve(outlet, cwd)
        if not outlet_path.is_file():
            sys.exit(f"Error: required input file not found: {outlet_path}")

    output_dir = cwd / outdir
    output_dir.mkdir(parents=True, exist_ok=True)

    # pysheds >= 0.3 API: rasters are returned, not stored on the grid
    grid = Grid.from_raster(str(dem_path))
    dem_raster = grid.read_raster(str(dem_path))

    outlet_geom = Point(xy) if xy is not None else _read_outlet(outlet_path, grid.crs, outlet_index)

    # Condition the DEM so every cell drains somewhere
    pit_filled = grid.fill_pits(dem_raster)
    flooded = grid.fill_depressions(pit_filled)
    inflated = grid.resolve_flats(flooded)

    fdir = grid.flowdir(inflated, dirmap=DIRMAP)
    acc = grid.accumulation(fdir, dirmap=DIRMAP)

    if all_outputs:
        grid.to_raster(inflated, str(output_dir / "dem_conditioned.tif"))
        grid.to_raster(fdir, str(output_dir / "flow_dir.tif"))
        grid.to_raster(acc, str(output_dir / "flow_accum.tif"))

    if not no_snap and not (acc > acc_threshold).any():
        sys.exit(f"Error: no cell has flow accumulation above {acc_threshold}; "
                 "lower --acc-threshold")

    line_mask = None
    if outlet_geom.geom_type == "Point":
        x, y = outlet_geom.x, outlet_geom.y
    else:
        line_mask = rasterize([outlet_geom], out_shape=grid.shape, transform=grid.affine,
                              all_touched=True, dtype=np.uint8).astype(bool)
        if not line_mask.any():
            sys.exit("Error: outlet line does not overlap the DEM")
        line_acc = np.where(line_mask, acc, -1)
        r, c = np.unravel_index(np.argmax(line_acc), line_acc.shape)
        x, y = _cell_center(grid, r, c)
        print(f"Outlet line crosses {np.count_nonzero(line_mask)} cells; "
              f"max accumulation {line_acc[r, c]:.0f}")
        # A line that misses the channel entirely is reduced to its
        # highest-accumulation cell and snapped like a point
        if not no_snap and line_acc[r, c] <= acc_threshold:
            print(f"Warning: outlet line does not cross a stream (accumulation > {acc_threshold}); "
                  "snapping its highest-accumulation cell instead")
            line_mask = None

    # A manually-marked pour point is rarely exactly on the channel, so move
    # it to the nearest cell whose accumulation exceeds the threshold
    if line_mask is None and not no_snap:
        snapped_x, snapped_y = grid.snap_to_mask(acc > acc_threshold, (x, y))
        print(f"Snapped pour point ({x:.3f}, {y:.3f}) -> ({snapped_x:.3f}, {snapped_y:.3f})")
        x, y = snapped_x, snapped_y

    if line_mask is not None:
        catch = _line_catchment(grid, fdir, acc, line_mask)
    else:
        catch = grid.catchment(x=x, y=y, fdir=fdir, dirmap=DIRMAP, xytype="coordinate")
    n_cells = int(np.count_nonzero(catch))
    if n_cells <= 1:
        print("Warning: catchment is a single cell; check the pour point or acc_threshold")

    # Clip the grid's view to the catchment's bounding box for all outputs below
    grid.clip_to(catch)
    catch_view = grid.view(catch, dtype=np.uint8, nodata=0)
    dem_view = grid.view(dem_raster, dtype=np.float64, nodata=np.nan)
    acc_view = grid.view(acc, dtype=np.float64, nodata=np.nan)

    grid.to_raster(catch_view, str(output_dir / "watershed.tif"))
    # Mask DEM cells outside the catchment so dem_clipped.tif is the
    # watershed itself, not its bounding box
    dem_masked = dem_view.copy()
    dem_masked[catch_view == 0] = np.nan
    grid.to_raster(dem_masked, str(output_dir / "dem_clipped.tif"))

    polygons = [shape(geom) for geom, value in grid.polygonize(catch_view) if value]
    cell_area = abs(grid.affine.a * grid.affine.e)
    watershed = gpd.GeoDataFrame(
        {"id": range(1, len(polygons) + 1),
         "area": [p.area for p in polygons]},
        geometry=polygons,
        crs=grid.crs.srs,
    )
    watershed.to_file(output_dir / "watershed.shp")

    streams = grid.extract_river_network(fdir, acc > acc_threshold, dirmap=DIRMAP)
    if streams["features"]:
        stream_net = gpd.GeoDataFrame.from_features(streams["features"], crs=grid.crs.srs)
        stream_net.to_file(output_dir / "streams.geojson", driver="GeoJSON")
        stream_net.to_file(output_dir / "streams.gpkg", driver="GPKG")
    else:
        stream_net = None
        print(f"Warning: no streams above accumulation {acc_threshold} in the catchment")

    print(f"Pour point : ({x:.3f}, {y:.3f})" + (" (main channel crossing)" if line_mask is not None else ""))
    print(f"Catchment  : {n_cells} cells, {n_cells * cell_area:,.1f} map units^2")
    if stream_net is not None:
        print(f"Streams    : {len(stream_net)} segments")

    if web_map and stream_net is not None:
        try:
            m = watershed.explore(tiles="Esri.WorldImagery", style_kwds={"fill": False, "color": "yellow"})
            stream_net.explore(m=m, color="cyan")
            m.save(output_dir / "streams_map.html")
            print(f"Web map saved to {output_dir / 'streams_map.html'}")
        except ImportError:
            print("Install folium and mapclassify for the web map: pip install folium mapclassify")

    if plot:
        _plot(grid, dem_masked, acc_view, watershed, stream_net, (x, y),
              outlet_geom if line_mask is not None else None)

    print(f"Wrote watershed.tif, watershed.shp, dem_clipped.tif, streams.* to {output_dir}")
    return output_dir


def _plot(grid, dem_view, acc_view, watershed, stream_net, pour_point, outlet_line=None):
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    extent = grid.extent

    im = ax1.imshow(dem_view, extent=extent, cmap="terrain", interpolation="nearest")
    fig.colorbar(im, ax=ax1, label="Elevation", shrink=0.8)
    ax1.set_title("Catchment elevation")

    acc_plot = np.where(acc_view > 0, acc_view, np.nan)
    im = ax2.imshow(acc_plot, extent=extent, cmap="PuRd", norm=LogNorm(), interpolation="nearest")
    fig.colorbar(im, ax=ax2, label="Upstream cells", shrink=0.8)
    ax2.set_title("Flow accumulation and streams")

    for ax in (ax1, ax2):
        watershed.boundary.plot(ax=ax, color="black", linewidth=1)
        if stream_net is not None:
            stream_net.plot(ax=ax, color="blue", linewidth=0.8)
        if outlet_line is not None:
            gpd.GeoSeries([outlet_line]).plot(ax=ax, color="red", linewidth=2, label="Outlet line")
        else:
            ax.plot(*pour_point, "r^", markersize=8, label="Pour point")
        ax.set_xlim(grid.bbox[0], grid.bbox[2])
        ax.set_ylim(grid.bbox[1], grid.bbox[3])
    ax1.legend(loc="upper right")
    plt.show()


def main():
    parser = argparse.ArgumentParser(
        prog="wsdpyshed",
        description="Delineate a watershed from a DEM and an outlet (point or line) using pysheds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  wsdpyshed --dem dem.tif --outlet pourpoint.shp                  # Pour point from a shapefile
  wsdpyshed --dem dem.tif --outlet crosssection.shp               # Line outlet (cross-section)
  wsdpyshed --dem dem.tif --xy 285612.0 2936416.7 --acc-threshold 500
  wsdpyshed --dem dem.tif --outlet pourpoint.shp --all-outputs --plot
        """,
    )
    parser.add_argument("--dem", required=True, help="Input DEM file path")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--outlet", help="Outlet shapefile path, a point or line (e.g. cross-section) layer")
    source.add_argument(
        "--xy", nargs=2, type=float, metavar=("X", "Y"),
        help="Pour point coordinates in the DEM's CRS, instead of --outlet",
    )
    parser.add_argument("--outdir", default="WSD", help="Output folder name (default: WSD)")
    parser.add_argument(
        "--acc-threshold", type=int, default=200,
        help="Flow accumulation (cell count) defining a stream; used to snap the "
             "pour point and to extract the stream network (default: 200)",
    )
    parser.add_argument(
        "--outlet-index", type=int, default=0,
        help="Feature index to use when the outlet layer has several points (default: 0)",
    )
    parser.add_argument(
        "--no-snap", action="store_true",
        help="Use the pour point as-is instead of snapping it to the nearest stream cell",
    )
    parser.add_argument(
        "--all-outputs", action="store_true",
        help="Also write the conditioned DEM, flow direction and flow accumulation rasters",
    )
    parser.add_argument(
        "--web-map", action="store_true",
        help="Also write an interactive streams_map.html (requires folium and mapclassify)",
    )
    parser.add_argument("--plot", action="store_true", help="Show the results in a matplotlib window")
    args = parser.parse_args()

    delineate_watershed(
        dem=args.dem,
        outlet=args.outlet,
        xy=tuple(args.xy) if args.xy else None,
        outdir=args.outdir,
        acc_threshold=args.acc_threshold,
        outlet_index=args.outlet_index,
        no_snap=args.no_snap,
        all_outputs=args.all_outputs,
        web_map=args.web_map,
        plot=args.plot,
    )


if __name__ == "__main__":
    main()
