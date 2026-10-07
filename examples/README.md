# Cataloging examples

Paths below are relative POSIX paths returned by object listing, not local filesystem paths. `path_pattern` is matched against the complete path relative to `--source`.

## Selection-only science files

Input: `science/scene_a.tif`, `science/scene_b.nc`.

```bash
dps-stac-item-generator --source s3://bucket/science/ --output_dir output --dry-run
```

Each selected raster is one Item with the sole asset key `asset`. IDs are its filename stem plus a 12-hex SHA-256 digest of the canonical full source URL (including extension).

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

Config files in this directory are exercised in tests. Use `--config examples/<name>.json`; all output IDs must be filesystem-safe.
