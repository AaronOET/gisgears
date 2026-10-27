#!/usr/bin/env python
"""
showshp - Display one or more shapefiles overlaid on a single map.

Prints each file's CRS, feature count, bounds and attribute table (first
10 rows unless --all is given). Layers
are reprojected onto the first layer's CRS so they line up, and larger
layers are drawn underneath smaller ones.
"""

import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt


def print_info(path, gdf, max_rows=10):
    """Print a layer's CRS, feature count, bounds and attribute table.

    Only the first ``max_rows`` rows of the table are printed; pass None to print all.
    """
    print(f"File     : {path}")
    print(f"CRS      : {gdf.crs}")
    print(f"Features : {len(gdf)}  ({', '.join(gdf.geom_type.unique())})")
    print(f"Bounds   : {gdf.total_bounds}")
    attrs = gdf.drop(columns="geometry")
    if not attrs.empty:
        if max_rows is not None and len(attrs) > max_rows:
            print(attrs.head(max_rows).to_string())
            print(f"... ({len(attrs) - max_rows} more rows; use --all to show all)")
        else:
            print(attrs.to_string())
    print()


def show_shapefiles(paths, label=None, show=True, max_rows=10):
    """Print info for each shapefile and plot them on one map. Returns the axes.

    ``max_rows`` limits how many attribute rows are printed per layer (None prints all).
    """
    _, ax = plt.subplots(figsize=(9, 9), constrained_layout=True)
    colors = plt.get_cmap("tab10").colors
    target_crs = None
    handles = []

    for i, path in enumerate(paths):
        gdf = gpd.read_file(path)
        print_info(path, gdf, max_rows=max_rows)

        # Reproject everything onto the first layer's CRS so layers line up
        if target_crs is None:
            target_crs = gdf.crs
        elif gdf.crs is not None and gdf.crs != target_crs:
            gdf = gdf.to_crs(target_crs)

        # Larger layers sit underneath so they don't cover smaller ones
        minx, miny, maxx, maxy = gdf.total_bounds
        zorder = -(maxx - minx) * (maxy - miny)

        color = colors[i % len(colors)]
        gdf.plot(ax=ax, facecolor=(*color, 0.25), edgecolor=color, linewidth=1.5, zorder=zorder,
                 markersize=30, color=color if gdf.geom_type.isin(["Point", "MultiPoint"]).all() else None)
        handles.append(plt.Line2D([], [], color=color, linewidth=3, label=Path(path).stem))

        if label and label in gdf.columns:
            for geom, text in zip(gdf.geometry, gdf[label]):
                pt = geom.representative_point()
                ax.annotate(str(text), (pt.x, pt.y), ha="center", va="center",
                            fontsize=9, color=color, fontweight="bold")

    ax.legend(handles=handles, loc="best")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.set_aspect("equal")
    ax.set_title(f"Shapefiles  [{target_crs}]")
    if show:
        plt.show()
    return ax


def main():
    parser = argparse.ArgumentParser(
        prog="showshp",
        description="Display one or more shapefiles overlaid on a single map, "
                    "and print each file's CRS, feature count, bounds and attribute table",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  showshp watershed.shp
  showshp thiessen.shp -l Station          # Label features by a column
  showshp thiessen.shp watershed.shp       # Overlay several layers
  showshp thiessen.shp -a                  # Print every attribute row
        """,
    )
    parser.add_argument("shp", nargs="+", type=Path, help="Path(s) to .shp files")
    parser.add_argument(
        "-l", "--label", metavar="COLUMN",
        help="Attribute column to write on each feature (e.g. Station)",
    )
    parser.add_argument(
        "-a", "--all", action="store_true",
        help="Print the full attribute table (default: first 10 rows)",
    )
    args = parser.parse_args()

    missing = [str(p) for p in args.shp if not p.exists()]
    if missing:
        raise SystemExit(f"File(s) not found: {', '.join(missing)}")
    show_shapefiles(args.shp, label=args.label, max_rows=None if args.all else 10)


if __name__ == "__main__":
    main()
