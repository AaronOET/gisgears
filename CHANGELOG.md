# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.5.1] - 2026-10-26

### Changed

- `wsdpyshed` delineates every feature of a multi-point or multi-line outlet layer (and every repeated `--xy`), labeling each watershed with its outlet id and nesting upstream sub-basins; `--outlet-index` now defaults to all features. The stream network is limited to the watersheds instead of their bounding box.

### Fixed

- `wsdpyshed` writes `streams.geojson` in WGS84 (RFC 7946), so it displays in the right place even when the DEM has a non-EPSG CRS that some GDAL versions leave out of the GeoJSON; `streams.gpkg` stays in the DEM's CRS.

## [0.5.0] - 2026-10-24

### Added

- `wsdsmooth` tool to smooth the boundary of a watershed polygon shapefile with a configurable moving-average filter size.

## [0.4.0] - 2026-10-24

### Added

- `wsdpyshed` tool to delineate a watershed and its stream network from a DEM and an outlet (point or line shapefile, or x/y) using pysheds, with a configurable accumulation threshold.

## [0.3.0] - 2026-10-24

### Added

- `showtable.list_layers()` and `showtable --list-layers` to list the layers in a GeoPackage.

## [0.2.0] - 2026-10-24

### Added

- `showtif` tool to display a DEM GeoTIFF with an elevation colormap and hillshade.
- `showshp` tool to display one or more shapefiles overlaid on a single map.
- `showtable` tool to print the attribute table of a shapefile or GeoPackage layer.

## [0.1.0] - 2026-08-27

### Added

- `wsdgen` tool to delineate a watershed from a DEM and an outlet layer (point or line).
- `gisgears` / `gisgears-info` command-line entry points listing available tools.
