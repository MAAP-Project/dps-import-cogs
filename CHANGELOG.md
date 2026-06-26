# Changelog

## [0.1.0] - 2025-12-12

Initial release of the MAAP DPS algorithm for generating STAC item metadata for existing Cloud Optimized GeoTIFF assets in object storage.

### Added

- Added the `GenerateCogStacItems` DPS algorithm at version `v0.1`.
- Added direct Python invocation through `main.py` for local STAC item generation.
- Added object storage listing for source locations such as S3 paths.
- Added filtering for GeoTIFF assets before STAC item creation.
- Added STAC item generation with `rio-stac` and catalog output with `pystac`.
- Added projection and raster metadata handling for generated STAC items.
- Added MAAP DPS wrapper scripts, including positional and named-argument execution paths.
- Added support for direct bucket access and MAAP-compatible cloud raster defaults.

### Fixed

- Improved generated STAC item IDs.
- Fixed Fmask nodata handling.
- Fixed bbox serialization.
- Set missing `proj:transform` and `proj:shape` values when available.

### Documentation

- Documented local usage with `uv run main.py`.
- Documented required inputs and generated STAC catalog outputs.
