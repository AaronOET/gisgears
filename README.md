# GISGEARS

A collection of Python tools for GIS/hydrology raster and vector analysis.

> **WhiteboxTools**: `wsdgen` depends on the WhiteboxTools executable, which the `whitebox` Python package downloads automatically the first time it runs.

## Installation

```bash
pip install gisgears
```

## Features

- **wsdgen**: Delineate a watershed from a DEM and an outlet layer (point or line)

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
```

### Python API

```python
from gisgears import wsdgen

# Delineate a watershed (written to WSD/watershed.tif, watershed.shp, watershed_smooth.shp)
wsdgen.delineate_watershed(dem="dem.tif", outlet="outlet.shp")
```

## Notes

- The outlet layer may be a point shapefile (a single manually-marked outlet) or a line shapefile (e.g. a cross-section at the watershed outlet); `wsdgen` detects the geometry type automatically.
- By default only the final `watershed.tif`, `watershed.shp` and `watershed_smooth.shp` are written to the `WSD/` output directory; pass `--all-outputs` to also keep intermediate files (breached DEM, D8 pointer, flow accumulation, snapped outlet, etc.) there instead of a temporary folder.
