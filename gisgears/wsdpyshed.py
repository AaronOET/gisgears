#!/usr/bin/env python
"""
wsdpyshed - Delineate watersheds from a DEM and outlets (points or lines) using pysheds.

A pure-Python alternative to wsdgen (no WhiteboxTools executable needed).
Given a DEM raster and one or more outlets - a point or line shapefile, or
x/y coordinates in the DEM's CRS - this tool conditions the DEM (fills pits
and depressions, resolves flats), computes D8 flow direction and
accumulation, snaps each point outlet onto the nearest cell whose
accumulation exceeds the threshold, delineates the catchments, and extracts
the stream network inside them. A line outlet (e.g. a cross-section at the
watershed outlet) is rasterized, and its catchment is the union of
everything draining to any cell the line crosses.

Every outlet gets its own watershed, labeled with the outlet's id (1, 2, ...
in feature order). When one outlet lies upstream of another, the downstream
watershed excludes the upstream one, so the outputs are nested sub-basins.
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


def _read_outlets(outlet_path, dem_crs, index=None):
    """
    Return {id: geometry} for the features of a point or line layer, in the
    DEM's CRS. Ids are 1-based feature positions; index picks a single
    feature (0-based) instead of all of them.
    """
    features = gpd.read_file(outlet_path)
    if features.empty:
        sys.exit(f"Error: outlet layer has no features: {outlet_path}")
    if not features.geom_type.isin(["Point", "MultiPoint", "LineString", "MultiLineString"]).all():
        sys.exit(f"Error: outlet layer must be a point or line layer: {outlet_path}")
    if index is not None and not 0 <= index < len(features):
        sys.exit(f"Error: outlet index {index} out of range (layer has {len(features)} features)")

    if features.crs is not None:
        features = features.to_crs(dem_crs.srs)
    else:
        print("Warning: outlet layer has no CRS; assuming it matches the DEM")

    geoms = {i + 1: geom for i, geom in enumerate(features.geometry)}
    if index is not None:
        print(f"Outlet layer has {len(features)} features; using feature {index}")
        return {index + 1: geoms[index + 1]}
    print(f"Outlet layer has {len(features)} feature(s); delineating each")
    return geoms


def _cell_center(grid, row, col):
    return grid.affine * (col + 0.5, row + 0.5)


def _cell_index(grid, x, y):
    col, row = ~grid.affine * (x, y)
    return int(np.floor(row)), int(np.floor(col))


def _catchment(grid, fdir, acc, seed_mask):
    """
    Union of the catchments of every cell in seed_mask. Cells are visited in
    descending accumulation order, and a cell already inside the union is
    skipped because its own catchment is contained in it - so a cross-section
    over one channel usually needs a single catchment call.
    """
    rows, cols = np.nonzero(seed_mask)
    order = np.argsort(np.asarray(acc)[rows, cols])[::-1]
    union = np.zeros(grid.shape, dtype=bool)
    for r, c in zip(rows[order], cols[order]):
        if union[r, c]:
            continue
        catch = grid.catchment(x=c, y=r, fdir=fdir, dirmap=DIRMAP, xytype="index")
        union |= np.asarray(catch, dtype=bool)
    return union


def _outlet_seeds(grid, acc, geom, acc_threshold, no_snap, label):
    """
    Return (seed_mask, pour_point) for one outlet: the cells whose catchments
    make up its watershed, and the coordinate reported for it. A line that
    crosses a stream keeps all its cells; a point - or a line that misses the
    channel - is reduced to one cell and snapped unless no_snap is set.
    Returns (None, None) when the outlet is off the DEM.
    """
    if geom.geom_type in ("LineString", "MultiLineString", "MultiPoint"):
        is_line = geom.geom_type != "MultiPoint"
        cells = rasterize([geom], out_shape=grid.shape, transform=grid.affine,
                          all_touched=is_line, dtype=np.uint8).astype(bool)
        if not cells.any():
            print(f"Warning: outlet {label} does not overlap the DEM; skipped")
            return None, None
        cells_acc = np.where(cells, acc, -1)
        r, c = np.unravel_index(np.argmax(cells_acc), cells_acc.shape)
        x, y = _cell_center(grid, r, c)
        print(f"Outlet {label}: {geom.geom_type} covers {np.count_nonzero(cells)} cells; "
              f"max accumulation {cells_acc[r, c]:.0f}")
        if no_snap or cells_acc[r, c] > acc_threshold:
            return cells, (x, y)
        # An outlet that misses the channel entirely is reduced to its
        # highest-accumulation cell and snapped like a point
        print(f"Warning: outlet {label} does not cross a stream (accumulation > {acc_threshold}); "
              "snapping its highest-accumulation cell instead")
    else:
        x, y = geom.x, geom.y
        r, c = _cell_index(grid, x, y)
        if not (0 <= r < grid.shape[0] and 0 <= c < grid.shape[1]):
            print(f"Warning: outlet {label} ({x:.3f}, {y:.3f}) is outside the DEM; skipped")
            return None, None

    # A manually-marked pour point is rarely exactly on the channel, so move
    # it to the nearest cell whose accumulation exceeds the threshold
    if not no_snap:
        snapped_x, snapped_y = grid.snap_to_mask(acc > acc_threshold, (x, y))
        print(f"Outlet {label}: snapped pour point ({x:.3f}, {y:.3f}) -> "
              f"({snapped_x:.3f}, {snapped_y:.3f})")
        x, y = snapped_x, snapped_y
        r, c = _cell_index(grid, x, y)
    seed_mask = np.zeros(grid.shape, dtype=bool)
    seed_mask[r, c] = True
    return seed_mask, (x, y)


def delineate_watershed(dem, outlet=None, xy=None, outdir="WSD", acc_threshold=200,
                        outlet_index=None, no_snap=False, all_outputs=False,
                        web_map=False, plot=False, cwd=None) -> Path:
    """
    Delineate watersheds from a DEM and one or more outlets (points or lines) using pysheds.

    Args:
        dem (str): Path to the input DEM raster
        outlet (str): Path to a point or line shapefile holding the outlets;
            reprojected to the DEM's CRS if needed. Each feature yields its
            own watershed, labeled 1, 2, ... in feature order. A line (e.g. a
            cross-section) yields the catchment draining to any cell it
            crosses. Ignored when xy is given
        xy (tuple or list): Pour point (x, y) in the DEM's CRS, or a list of
            them, instead of outlet
        outdir (str): Output folder name (default: WSD)
        acc_threshold (int): Flow accumulation (cell count) above which a cell
            is treated as a stream; used both to snap the pour points and to
            extract the stream network (default: 200)
        outlet_index (int): Use only this feature (0-based) of the outlet
            layer instead of all of them (default: None, all features)
        no_snap (bool): Use the pour points as-is instead of snapping them to
            the nearest stream cell (a line outlet is only snapped when no
            cell it crosses exceeds acc_threshold)
        all_outputs (bool): Also write the conditioned DEM, flow direction
            and flow accumulation rasters (full DEM extent)
        web_map (bool): Also write an interactive streams_map.html
            (requires folium and mapclassify)
        plot (bool): Show the DEM, catchments and stream network in matplotlib
        cwd (Path): Working directory to resolve relative paths against
            (defaults to the current directory)

    Returns:
        Path: Output directory containing watershed.tif (cells labeled with
            the outlet id), watershed.shp (one row per outlet), dem_clipped.tif,
            streams.gpkg and streams.geojson
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

    if xy is not None:
        points = [xy] if np.ndim(xy) == 1 else xy
        outlets = {i + 1: Point(p) for i, p in enumerate(points)}
    else:
        outlets = _read_outlets(outlet_path, grid.crs, outlet_index)

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

    catchments = []
    for label, geom in outlets.items():
        seed_mask, pour_point = _outlet_seeds(grid, acc, geom, acc_threshold, no_snap, label)
        if seed_mask is None:
            continue
        catchments.append((label, geom, pour_point, _catchment(grid, fdir, acc, seed_mask)))
    if not catchments:
        sys.exit("Error: no outlet overlaps the DEM")

    # Paint the largest catchments first so one nested inside another (an
    # upstream outlet) keeps its own label - the downstream watershed then
    # covers only the area between the two outlets
    labels = np.zeros(grid.shape, dtype=np.int32)
    for label, _, _, catch in sorted(catchments, key=lambda item: -np.count_nonzero(item[3])):
        labels[catch] = label
    labels = Raster(labels, viewfinder=fdir.viewfinder)

    # Clip the grid's view to the catchments' bounding box for all outputs below
    grid.clip_to(labels)
    catch_view = grid.view(labels, dtype=np.int32, nodata=0)
    dem_view = grid.view(dem_raster, dtype=np.float64, nodata=np.nan)
    acc_view = grid.view(acc, dtype=np.float64, nodata=np.nan)

    grid.to_raster(catch_view, str(output_dir / "watershed.tif"))
    # Mask DEM cells outside the catchments so dem_clipped.tif is the
    # watersheds themselves, not their bounding box
    dem_masked = dem_view.copy()
    dem_masked[catch_view == 0] = np.nan
    grid.to_raster(dem_masked, str(output_dir / "dem_clipped.tif"))

    parts = [(int(value), shape(geom)) for geom, value in grid.polygonize(catch_view) if value]
    cell_area = abs(grid.affine.a * grid.affine.e)
    watershed = gpd.GeoDataFrame(
        {"id": [label for label, _ in parts]},
        geometry=[part for _, part in parts],
        crs=grid.crs.srs,
    ).dissolve(by="id", as_index=False)
    watershed["id"] = watershed["id"].astype(np.int32)
    watershed["area"] = watershed.area
    watershed.to_file(output_dir / "watershed.shp")

    # Only extract streams inside the watersheds, not the whole bounding box
    stream_mask = Raster((np.asarray(acc_view) > acc_threshold) & (np.asarray(catch_view) > 0),
                         viewfinder=catch_view.viewfinder)
    streams = grid.extract_river_network(fdir, stream_mask, dirmap=DIRMAP)
    if streams["features"]:
        stream_net = gpd.GeoDataFrame.from_features(streams["features"], crs=grid.crs.srs)
        # GeoJSON is WGS84 by definition (RFC 7946); readers that ignore or
        # can't write a non-EPSG "crs" member would otherwise misplace it
        stream_net.to_crs(epsg=4326).to_file(output_dir / "streams.geojson", driver="GeoJSON")
        stream_net.to_file(output_dir / "streams.gpkg", driver="GPKG")
    else:
        stream_net = None
        print(f"Warning: no streams above accumulation {acc_threshold} in the catchments")

    for label, geom, (x, y), _ in catchments:
        n_cells = int(np.count_nonzero(np.asarray(catch_view) == label))
        crossing = " (main channel crossing)" if geom.geom_type.endswith("LineString") else ""
        print(f"Watershed {label}: pour point ({x:.3f}, {y:.3f}){crossing}; "
              f"{n_cells} cells, {n_cells * cell_area:,.1f} map units^2")
        if n_cells <= 1:
            print(f"Warning: watershed {label} is at most a single cell; "
                  "check the pour point or acc_threshold")
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
        _plot(grid, dem_masked, acc_view, watershed, stream_net,
              {label: pour_point for label, _, pour_point, _ in catchments},
              [geom for _, geom, _, _ in catchments if geom.geom_type.endswith("LineString")])

    print(f"Wrote watershed.tif, watershed.shp, dem_clipped.tif, streams.* to {output_dir}")
    return output_dir


def _plot(grid, dem_view, acc_view, watershed, stream_net, pour_points, outlet_lines=()):
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
        if outlet_lines:
            gpd.GeoSeries(outlet_lines).plot(ax=ax, color="red", linewidth=2, label="Outlet line")
        else:
            xs, ys = zip(*pour_points.values())
            ax.plot(xs, ys, "r^", markersize=8, label="Pour point")
        if len(pour_points) > 1:
            for label, (x, y) in pour_points.items():
                ax.annotate(str(label), (x, y), xytext=(4, 4), textcoords="offset points",
                            color="red", fontweight="bold")
        ax.set_xlim(grid.bbox[0], grid.bbox[2])
        ax.set_ylim(grid.bbox[1], grid.bbox[3])
    ax1.legend(loc="upper right")
    plt.show()


def main():
    parser = argparse.ArgumentParser(
        prog="wsdpyshed",
        description="Delineate watersheds from a DEM and one or more outlets (points or lines) using pysheds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  wsdpyshed --dem dem.tif --outlet pourpoints.shp                 # One watershed per point
  wsdpyshed --dem dem.tif --outlet crosssections.shp              # One watershed per line (cross-section)
  wsdpyshed --dem dem.tif --outlet crosssections.shp --outlet-index 0   # First feature only
  wsdpyshed --dem dem.tif --xy 285612.0 2936416.7 --acc-threshold 500
  wsdpyshed --dem dem.tif --xy 285612.0 2936416.7 --xy 286100.0 2937020.5
  wsdpyshed --dem dem.tif --outlet pourpoints.shp --all-outputs --plot
        """,
    )
    parser.add_argument("--dem", required=True, help="Input DEM file path")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--outlet",
        help="Outlet shapefile path, a point or line (e.g. cross-section) layer; "
             "each feature yields its own watershed",
    )
    source.add_argument(
        "--xy", nargs=2, type=float, action="append", metavar=("X", "Y"),
        help="Pour point coordinates in the DEM's CRS, instead of --outlet; repeat for several outlets",
    )
    parser.add_argument("--outdir", default="WSD", help="Output folder name (default: WSD)")
    parser.add_argument(
        "--acc-threshold", type=int, default=200,
        help="Flow accumulation (cell count) defining a stream; used to snap the "
             "pour points and to extract the stream network (default: 200)",
    )
    parser.add_argument(
        "--outlet-index", type=int, default=None,
        help="Use only this feature (0-based) of the outlet layer (default: all features)",
    )
    parser.add_argument(
        "--no-snap", action="store_true",
        help="Use the pour points as-is instead of snapping them to the nearest stream cell",
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
        xy=[tuple(p) for p in args.xy] if args.xy else None,
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
