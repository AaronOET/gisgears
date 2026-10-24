#!/usr/bin/env python
"""
Command-line utility to display descriptions of gisgears functionality.
"""

import argparse
import sys
from textwrap import dedent

TOOL_DESCRIPTIONS = {
    'wsdgen': """
        Delineate a watershed from a DEM and an outlet layer (point or line).

        Breaches depressions, computes D8 flow direction/accumulation, snaps
        the outlet onto the stream, delineates the watershed, and converts
        the result to polygon shapefiles (raw and boundary-smoothed).
        Requires the WhiteboxTools executable, downloaded automatically by
        the `whitebox` Python package on first use.

        Examples:
            wsdgen --dem dem.tif --outlet outlet.shp                     # Point outlet
            wsdgen --dem dem.tif --outlet crosssection.shp --all-outputs # Keep intermediates
    """,
    'showtif': """
        Display a DEM GeoTIFF with an elevation colormap and hillshade.

        Prints the raster's CRS, size, cell size, nodata value and
        elevation statistics, then plots the elevation and a hillshade
        side by side.

        Examples:
            showtif dem.tif
    """,
    'showshp': """
        Display one or more shapefiles overlaid on a single map.

        Prints each file's CRS, feature count, bounds and attribute table.
        Layers are reprojected onto the first layer's CRS so they line up.

        Examples:
            showshp watershed.shp
            showshp thiessen.shp -l Station        # Label features by a column
            showshp thiessen.shp watershed.shp     # Overlay several layers
    """,
    'showtable': """
        Print the attribute table of a shapefile or GeoPackage layer.

        Prints the layer's CRS, feature count and field types, followed by
        the attribute table. GeoPackages with several layers are listed.

        Examples:
            showtable thiessen.shp
            showtable thiessen.shp -c Station -g   # Selected columns plus geometry WKT
            showtable data.gpkg -l roads -n 20     # Pick a layer, first 20 rows
    """,
}


def main():
    parser = argparse.ArgumentParser(
        prog='gisgears-info',
        description='Display descriptions of gisgears commands',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'tool',
        nargs='?',
        choices=list(TOOL_DESCRIPTIONS.keys()),
        help='Tool name to describe (omit to list all tools)',
    )
    args = parser.parse_args()

    if args.tool:
        print(f"\n--- {args.tool} ---")
        print(dedent(TOOL_DESCRIPTIONS[args.tool]))
    else:
        print("\nGISGEARS — GIS/hydrology analysis commands\n")
        for tool, desc in TOOL_DESCRIPTIONS.items():
            first_line = dedent(desc).strip().splitlines()[0]
            print(f"  {tool:<14} {first_line}")
        print("\nRun 'gisgears-info <tool>' for details on a specific command.")


if __name__ == "__main__":
    main()
