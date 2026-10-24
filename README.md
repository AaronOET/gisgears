# GISGEARS

A collection of Python tools for GIS/hydrology raster and vector analysis.

> **WhiteboxTools**: `wsdgen` depends on the WhiteboxTools executable, which the `whitebox` Python package downloads automatically the first time it runs.

## Installation

```bash
pip install gisgears
```

## Features

- **wsdgen**: Delineate a watershed from a DEM and an outlet layer (point or line)
- **wsdpyshed**: Delineate a watershed and stream network from a DEM and an outlet (point or line) using pysheds (no WhiteboxTools needed)
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

# Delineate with pysheds from a pour point shapefile or x/y coordinates
wsdpyshed --dem dem.tif --outlet pourpoint.shp
wsdpyshed --dem dem.tif --outlet crosssection.shp   # line outlet
wsdpyshed --dem dem.tif --xy 285612.0 2936416.7 --acc-threshold 500 --plot

# Inspect a DEM (prints CRS/size/stats, plots elevation + hillshade)
showtif dem.tif

# Overlay shapefiles on one map, labelling features by a column
showshp WSD/watershed.shp outlet.shp -l Station

# Print an attribute table (selected columns, with geometry as WKT)
showtable thiessen.shp -c Station -g
showtable data.gpkg -l roads -n 20
showtable data.gpkg --list-layers
```

### Python API

```python
from gisgears import wsdgen

# Delineate a watershed (written to WSD/watershed.tif, watershed.shp, watershed_smooth.shp)
wsdgen.delineate_watershed(dem="dem.tif", outlet="outlet.shp")

from gisgears import wsdpyshed

# Same idea with pysheds; also writes dem_clipped.tif and streams.gpkg/.geojson to WSD/
wsdpyshed.delineate_watershed(dem="dem.tif", outlet="pourpoint.shp", acc_threshold=200)

from gisgears import showtif, showshp, showtable

showtif.show_dem("dem.tif")
showshp.show_shapefiles(["WSD/watershed.shp", "outlet.shp"], label="Station")
table = showtable.show_table("thiessen.shp", columns=["Station"])  # returns a DataFrame
layers = showtable.list_layers("data.gpkg")  # [(name, geometry type), ...]
```

## Notes

- The outlet layer may be a point shapefile (a single manually-marked outlet) or a line shapefile (e.g. a cross-section at the watershed outlet); `wsdgen` detects the geometry type automatically.
- By default only the final `watershed.tif`, `watershed.shp` and `watershed_smooth.shp` are written to the `WSD/` output directory; pass `--all-outputs` to also keep intermediate files (breached DEM, D8 pointer, flow accumulation, snapped outlet, etc.) there instead of a temporary folder.
- `wsdpyshed` takes a point or line outlet (`--outlet`, reprojected to the DEM's CRS if needed; pick a feature with `--outlet-index`) or coordinates (`--xy`). The pour point is snapped to the nearest cell whose flow accumulation exceeds `--acc-threshold` (default 200, also used for the stream network) unless `--no-snap` is given. A line outlet (e.g. a cross-section) is rasterized and the watershed is everything draining to any cell it crosses; if it crosses no stream cell, its highest-accumulation cell is snapped like a point. Outputs go to `WSD/` by default: `watershed.tif`, `watershed.shp`, `dem_clipped.tif`, `streams.gpkg` and `streams.geojson`; `--all-outputs` adds the conditioned DEM, flow direction and flow accumulation rasters, and `--web-map` writes `streams_map.html` (requires `folium` and `mapclassify`).
