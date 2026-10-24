# GISGEARS

A collection of Python tools for GIS/hydrology raster and vector analysis.

> **WhiteboxTools**: `wsdgen` depends on the WhiteboxTools executable, which the `whitebox` Python package downloads automatically the first time it runs.

## Installation

```bash
pip install gisgears
```

## Features

- **wsdgen**: Delineate a watershed from a DEM and an outlet layer (point or line)
- **showtif**: Display a DEM GeoTIFF with an elevation colormap and hillshade
- **showshp**: Display one or more shapefiles overlaid on a single map
- **showtable**: Print the attribute table of a shapefile or GeoPackage layer

## Usage

### Command-line

```bash
# List all available commands
gisgears-info

# Delineate a watershed from a point outlet
wsdgen --dem dem.tif --outlet outlet.shp

# Delineate a watershed from a line outlet (e.g. a cross-section), keeping intermediates
wsdgen --dem dem.tif --outlet crosssection.shp --all-outputs

# Use a coarser/finer boundary-smoothing filter
wsdgen --dem dem.tif --outlet outlet.shp --smooth-filter 15

# Inspect a DEM (prints CRS/size/stats, plots elevation + hillshade)
showtif dem.tif

# Overlay shapefiles on one map, labelling features by a column
showshp WSD/watershed.shp outlet.shp -l Station

# Print an attribute table (selected columns, with geometry as WKT)
showtable thiessen.shp -c Station -g
showtable data.gpkg -l roads -n 20
```

### Python API

```python
from gisgears import wsdgen

# Delineate a watershed (written to WSD/watershed.tif, watershed.shp, watershed_smooth.shp)
wsdgen.delineate_watershed(dem="dem.tif", outlet="outlet.shp")

from gisgears import showtif, showshp, showtable

showtif.show_dem("dem.tif")
showshp.show_shapefiles(["WSD/watershed.shp", "outlet.shp"], label="Station")
table = showtable.show_table("thiessen.shp", columns=["Station"])  # returns a DataFrame
```

## Notes

- The outlet layer may be a point shapefile (a single manually-marked outlet) or a line shapefile (e.g. a cross-section at the watershed outlet); `wsdgen` detects the geometry type automatically.
- By default only the final `watershed.tif`, `watershed.shp` and `watershed_smooth.shp` are written to the `WSD/` output directory; pass `--all-outputs` to also keep intermediate files (breached DEM, D8 pointer, flow accumulation, snapped outlet, etc.) there instead of a temporary folder.
