#!/usr/bin/env python
"""
showtable - Print the attribute table of a shapefile or GeoPackage layer.

Prints the layer's CRS, feature count and field types, followed by the
attribute table (first 10 rows unless --all is given). For a GeoPackage with several layers, the layers are
listed and the first one is shown unless another is chosen.
"""

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio


def list_layers(path, verbose=True):
    """Return the layers in a GeoPackage (or other vector file) as (name, geometry type) pairs."""
    layers = [(name, geom_type) for name, geom_type in pyogrio.list_layers(path)]
    if verbose:
        print(f"Layers in {path}:")
        for name, geom_type in layers:
            print(f"  {name}  ({geom_type})")
        print()
    return layers


def show_table(path, layer=None, rows=10, columns=None, geometry=False):
    """Print layer info and its attribute table. Returns the table as a DataFrame.

    Only the first ``rows`` rows are printed and returned; pass None for all rows.
    """
    layers = pyogrio.list_layers(path)  # array of [name, geometry type]
    if len(layers) > 1:
        list_layers(path)
    if layer is None:
        layer = layers[0][0]
    elif layer not in layers[:, 0]:
        raise SystemExit(f"Layer '{layer}' not found in {path}")

    gdf = gpd.read_file(path, layer=layer)

    print(f"File     : {path}")
    print(f"Layer    : {layer}")
    print(f"CRS      : {gdf.crs}")
    print(f"Features : {len(gdf)}")
    print()

    print("Fields:")
    for col, dtype in gdf.drop(columns="geometry").dtypes.items():
        print(f"  {col:<20} {dtype}")
    print()

    table = pd.DataFrame(gdf.drop(columns="geometry"))

    if columns:
        missing = [c for c in columns if c not in table.columns]
        if missing:
            raise SystemExit(f"Column(s) not found: {', '.join(missing)}")
        table = table[columns]

    if geometry:
        table["geometry"] = gdf.geometry.to_wkt()

    hidden = 0
    if rows is not None and len(table) > rows:
        hidden = len(table) - rows
        table = table.head(rows)

    with pd.option_context("display.max_rows", None, "display.max_columns", None,
                           "display.width", None, "display.max_colwidth", 60):
        print(table.to_string() if not table.empty else "(no attribute fields)")
    if hidden:
        print(f"... ({hidden} more rows; use --all to show all)")
    return table


def main():
    parser = argparse.ArgumentParser(
        prog="showtable",
        description="Print the attribute table of a shapefile (.shp) or GeoPackage (.gpkg) layer, "
                    "along with its CRS, feature count and field types",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  showtable thiessen.shp
  showtable thiessen.shp -c Station -g     # Selected columns plus geometry WKT
  showtable data.gpkg -l roads -n 20       # Pick a layer, first 20 rows
  showtable thiessen.shp -a                # Print every row
  showtable data.gpkg --list-layers        # List layers only
        """,
    )
    parser.add_argument("path", type=Path, help="Path to a .shp or .gpkg file")
    parser.add_argument("-l", "--layer",
                        help="Layer name inside a GeoPackage (default: first layer)")
    parser.add_argument("-L", "--list-layers", action="store_true",
                        help="List the layers in the file and exit")
    rows_group = parser.add_mutually_exclusive_group()
    rows_group.add_argument("-n", "--rows", type=int, default=10, metavar="N",
                            help="Show only the first N rows (default: 10)")
    rows_group.add_argument("-a", "--all", action="store_true",
                            help="Show all rows")
    parser.add_argument("-c", "--columns", nargs="+", metavar="COL",
                        help="Show only these columns")
    parser.add_argument("-g", "--geometry", action="store_true",
                        help="Include the geometry column as WKT text")
    args = parser.parse_args()

    if not args.path.exists():
        raise SystemExit(f"File not found: {args.path}")
    if args.list_layers:
        list_layers(args.path)
        return
    show_table(args.path, layer=args.layer, rows=None if args.all else args.rows,
               columns=args.columns, geometry=args.geometry)


if __name__ == "__main__":
    main()
