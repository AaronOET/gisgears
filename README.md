# GISGEARS

A collection of Python tools for GIS/hydrology raster and vector analysis.

> **WhiteboxTools**: `wsdgen` depends on the WhiteboxTools executable, which the `whitebox` Python package downloads automatically the first time it runs.

## Installation

```bash
pip install gisgears
```

## Features

- **wsdgen**: Delineate a watershed from a DEM and an outlet layer (point or line)
- **wsdpyshed**: Delineate watersheds and the stream network from a DEM and one or more outlets (points or lines) using pysheds (no WhiteboxTools needed)
- **wsdsmooth**: Smooth the boundary of a watershed polygon shapefile
- **showtif**: Display a DEM GeoTIFF with an elevation colormap, optionally alongside a hillshade
- **showtif2**: Same as `showtif`, but reads the DEM and computes the hillshade with [terrio](https://terrio.opengeos.org) (no GDAL)
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

# Extract a sparser stream network (cells with flow accumulation > 500)
wsdgen --dem dem.tif --outlet outlet.shp --acc-threshold 500

# Delineate with pysheds from a pour point shapefile or x/y coordinates
wsdpyshed --dem dem.tif --outlet pourpoint.shp
wsdpyshed --dem dem.tif --outlet crosssections.shp  # line outlets, one watershed per line
wsdpyshed --dem dem.tif --xy 285612.0 2936416.7 --acc-threshold 500 --plot

# Smooth a watershed boundary (default filter 9, written to WSD/<name>_smooth.shp)
wsdsmooth WSD/watershed.shp
wsdsmooth watershed.shp --filter 15 -o basin_smooth.shp

# Inspect a DEM (prints CRS/size/stats, plots elevation; --hillshade adds a hillshade)
showtif dem.tif
showtif dem.tif --hillshade
showtif2 dem.tif --hillshade  # same, using terrio instead of rasterio

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

# Delineate a watershed (written to WSD/watershed.tif, watershed.shp, watershed_smooth.shp,
# streams.shp, streams.gpkg, streams.geojson)
wsdgen.delineate_watershed(dem="dem.tif", outlet="outlet.shp", acc_threshold=200)

from gisgears import wsdpyshed

# Same idea with pysheds; also writes dem_clipped.tif and streams.gpkg/.geojson to WSD/
wsdpyshed.delineate_watershed(dem="dem.tif", outlet="pourpoint.shp", acc_threshold=200)

from gisgears import wsdsmooth

# Smooth a watershed boundary (written to WSD/watershed_smooth.shp)
wsdsmooth.smooth_watershed("WSD/watershed.shp", filter_size=9)

from gisgears import showtif, showshp, showtable

showtif.show_dem("dem.tif")

from gisgears import showtif2

showtif2.show_dem("dem.tif", hillshade=True)  # terrio-based, with hillshade
showshp.show_shapefiles(["WSD/watershed.shp", "outlet.shp"], label="Station")
table = showtable.show_table("thiessen.shp", columns=["Station"])  # returns a DataFrame
layers = showtable.list_layers("data.gpkg")  # [(name, geometry type), ...]
```

## Notes

- The outlet layer may be a point shapefile (a single manually-marked outlet) or a line shapefile (e.g. a cross-section at the watershed outlet); `wsdgen` detects the geometry type automatically.
- By default only the final `watershed.tif`, `watershed.shp`, `watershed_smooth.shp` and the stream network inside the watershed (`streams.shp` and `streams.gpkg` in the DEM's CRS, `streams.geojson` in WGS84) are written to the `WSD/` output directory; pass `--all-outputs` to also keep intermediate files (breached DEM, D8 pointer, flow accumulation, snapped outlet, stream raster, etc.) there instead of a temporary folder. Streams are cells whose flow accumulation exceeds `--acc-threshold` (cell count, default 200).
- `wsdpyshed` takes a point or line outlet layer (`--outlet`, reprojected to the DEM's CRS if needed) or coordinates (`--xy`, repeatable). Every feature or `--xy` pair gets its own watershed, labeled 1, 2, ... in order (the cell value in `watershed.tif` and the `id` field in `watershed.shp`); when one outlet is upstream of another, the downstream watershed excludes the upstream one, giving nested sub-basins. Use `--outlet-index` to delineate a single feature only. Each pour point is snapped to the nearest cell whose flow accumulation exceeds `--acc-threshold` (default 200, also used for the stream network) unless `--no-snap` is given. A line outlet (e.g. a cross-section) is rasterized and the watershed is everything draining to any cell it crosses; if it crosses no stream cell, its highest-accumulation cell is snapped like a point. Outputs go to `WSD/` by default: `watershed.tif`, `watershed.shp`, `dem_clipped.tif`, `streams.gpkg` (in the DEM's CRS) and `streams.geojson` (in WGS84, as GeoJSON requires); `--all-outputs` adds the conditioned DEM, flow direction and flow accumulation rasters, and `--web-map` writes `streams_map.html` (requires `folium` and `mapclassify`).
