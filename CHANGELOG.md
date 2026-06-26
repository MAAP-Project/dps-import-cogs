# Changelog

## [0.2.0](https://github.com/MAAP-Project/dps-import-cogs/compare/v0.1.0...v0.2.0) (2026-06-26)


### Features

* add named arguments to new run-named.sh script for OGC Application Packages ([#2](https://github.com/MAAP-Project/dps-import-cogs/issues/2)) ([7a1302c](https://github.com/MAAP-Project/dps-import-cogs/commit/7a1302c91d4031cbbf6f4dc95fcd1c20b234053e))
* add notebook showing how to submit jobs and query results ([4caaaf6](https://github.com/MAAP-Project/dps-import-cogs/commit/4caaaf61078bca183327f864375194310875cff8))
* add option to use direct bucket access ([a60eb7c](https://github.com/MAAP-Project/dps-import-cogs/commit/a60eb7cac1cb131aafef0bba6962a065b8fe8d82))
* add retry logic to catch intermittent errors ([983a8be](https://github.com/MAAP-Project/dps-import-cogs/commit/983a8be3878c87819de35a269d471fc46d871249))
* create DPS algorithm for generating STAC items for existing files ([9836ae9](https://github.com/MAAP-Project/dps-import-cogs/commit/9836ae9a65cee34d74aa69dd7253c79b53d536c8))
* only allow CRS definitions with meters as units ([cb675c1](https://github.com/MAAP-Project/dps-import-cogs/commit/cb675c18e2b1529c522428e9ccad03ad9dc3eb79))
* update to handle non-tif files ([#2](https://github.com/MAAP-Project/dps-import-cogs/issues/2)) ([521567d](https://github.com/MAAP-Project/dps-import-cogs/commit/521567d5d4be4f9e319e3b2a4d7d2bfb87970b0a)), closes [#1](https://github.com/MAAP-Project/dps-import-cogs/issues/1)
* update to use v2 of the HLS STAC Geoparquet ([0595fff](https://github.com/MAAP-Project/dps-import-cogs/commit/0595fffa28dfc12190d30f13c5f97a72e360946b))
* upgrade to v2 of hls-stac-geoparquet-archive ([4132de5](https://github.com/MAAP-Project/dps-import-cogs/commit/4132de52012ceff45acd2ad579a95bfb7402aa05))


### Bug Fixes

* convert bbox to string ([e85680c](https://github.com/MAAP-Project/dps-import-cogs/commit/e85680c21e8f9bedb71f5ae316bb90d559e26e16))
* fix Fmask nodata and set up run.sh with named args ([3d34d10](https://github.com/MAAP-Project/dps-import-cogs/commit/3d34d107e38b5f0cc6c1e6a39381b151c18421e5))
* improve item ids ([18bfd44](https://github.com/MAAP-Project/dps-import-cogs/commit/18bfd4438804c7c678e2c9bda4b4650ba45399f1))
* set cloud_defaults=True in configure_rio ([53060ee](https://github.com/MAAP-Project/dps-import-cogs/commit/53060ee1cbe8458218f9fc7d26ede03a0e14fb4f))
* set proj:transform and proj:shape if missing ([3b60f49](https://github.com/MAAP-Project/dps-import-cogs/commit/3b60f49a63a4447601cb5fbdcc28a4592de8c0a6))

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
