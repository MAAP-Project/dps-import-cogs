# Cataloging examples

Paths below are relative POSIX paths returned by object listing, not local filesystem paths. `path_pattern` is matched against the complete path relative to `--source`.

## Selection-only science files

Input paths relative to the source: `science/scene_a.tif`, `science/scene_b.nc`. Use [`selection-only.json`](selection-only.json) to select these science files and ignore other listed paths.

```bash
dps-stac-item-generator --source s3://bucket/input/ --output_dir output --config examples/selection-only.json --dry-run
```

The mapping is two Items, each with asset key `asset`: `science/scene_a.tif` and `science/scene_b.nc`. Each ID is its filename stem plus a 12-hex SHA-256 digest of the canonical full source URL (including extension).

## Directory per item: red/nir

Inputs: `tiles/32TPR/red.tif`, `tiles/32TPR/nir.tif`; another tile has its own directory. Use `directory-per-item.json` to make a single Item per tile. `datetime_template` is required for grouped mode, even if the date is a constant capture or a per-item value.

## Filename grouped scene_red / scene_nir

Inputs: `scenes/scene-1_red.tif`, `scenes/scene-1_nir.tif`. Use `filename-grouped.json`; each scene becomes one Item with `red` and `nir` assets.

## Gamma0 tile/date/scene polarizations

Inputs (and analogous sibling `33UUU` paths):

```text
32TPR/2026-01-01/source-A/gamma0_hh.tif
32TPR/2026-01-01/source-A/gamma0_hv.tif
32TPR/2026-01-01/source-A/thumbnail.png
```

`gamma0-grouped.json` yields `biomass-source-A-32TPR-2026-01-01`, with `hh`, `hv`, and `thumbnail` assets. A sibling tile creates a different Item despite identical basenames. PNG is explicitly mapped as an attachment and is not opened by rasterio.

## Raster plus thumbnail

Input paths relative to the source: `scene-1/raster.tif` and `scene-1/thumbnail.png`. Use [`raster-thumbnail.json`](raster-thumbnail.json):

```bash
dps-stac-item-generator --source s3://bucket/input/ --output_dir output --config examples/raster-thumbnail.json --dry-run
```

The mapping is one Item, `scene-1`, with `raster=scene-1/raster.tif` and `thumbnail=scene-1/thumbnail.png`. The PNG is a thumbnail attachment and is not opened as a raster.

Config files in this directory are exercised in tests. Use `--config examples/<name>.json`; all output IDs must be filesystem-safe.
