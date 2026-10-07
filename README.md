# DPS STAC Item Generator

Create STAC metadata for existing raster files in object storage (S3, Azure, GCS, etc.) or a local `file://` directory. The generator lists objects with `obstore`, applies extension filters, reads raster metadata with `rio-stac`, and writes a self-contained STAC catalog. It references the source assets without copying rasters.

## Quick start (no config)

```bash
uv sync --frozen
uv run --frozen main.py --source "s3://bucket/path/to/files/" --output_dir /tmp/stac-output
```

With no config, each selected raster becomes an Item with asset key `asset`. Its ID is a readable filename stem plus a 12-character SHA-256 digest of the canonical full source URL, including extension. This makes repeated basenames in different directories, prefixes, and formats distinct, independent of listing order. Moving or renaming a source changes its generated ID. `--legacy-naming` requests the prior path-based ID style where safe; collisions still fail.

## Optional path configuration

Pass `--config examples/filename-grouped.json` for path-based selection/grouping, and use `--dry-run` to inspect the mapping without raster reads or output publication. See [`examples/`](examples/README.md) for selection and grouping layouts, including a runnable two-tile RGB happy-face demo.

Config paths are POSIX object paths relative to `--source`, not absolute URLs or local filesystem paths. The single `path_pattern` regex is matched against the entire relative path (`fullmatch`); named captures may be substituted with `{capture}` in templates. Templates are substitution-only and do not evaluate expressions. Grouped configs require `item_id_template`, `asset_key_template`, `datetime_template` (ISO-8601 with timezone), and `reference_asset`. `required_assets` may list keys that each Item must contain. Selection-only configs omit `item_id_template` and retain safe per-file IDs and rio-stac datetime behavior.

Extension filters apply before pattern matching; exclusions always win. Configured `non_raster_assets` suffixes are added to the default `.tif,.tiff,.nc` allowlist, so explicitly mapped attachments such as `.png` are not silently dropped. An explicitly supplied `--include-extensions` replaces that allowlist; exclusions still win. Omit it to retain the config-aware defaults, especially when mapping attachments. Unmatched paths are counted in dry-run output.

Common config errors include invalid JSON/unknown fields, an invalid or non-matching regex, templates referencing absent captures, unsafe IDs/asset keys, missing required/reference assets, and duplicate IDs/asset keys. Plan validation occurs before raster metadata extraction. Listing is still needed for dry-run; manifests are not supported.

## MAAP interface and inputs

Register MAAP jobs through `dps-import-cogs.cwl`, the sole MAAP interface. This OGC Application Package uses CWL v1.2, Workflow ID `generate_stac_items`, and title **DPS STAC Item Generator**. The migration removes the legacy DPS configuration and shell wrappers; it keeps the Python generator's defaults and STAC output structure.

| CWL input | Default | Meaning |
| --- | --- | --- |
| `source` | Required | Object-storage URL or local directory URL to list |
| `region` | `us-west-2` | AWS region for the storage container |
| `include_extensions` | Omitted (effective default `.tif,.tiff,.nc`) | Comma-separated extensions; an explicit empty string includes all files |
| `exclude_extensions` | Empty string | Comma-separated extensions to exclude; exclusions override inclusions |
| `config` | Omitted | Optional JSON cataloging configuration |

CWL exposes `config` but not `--dry-run`: the workflow contract returns a catalog `Directory`, while dry-run intentionally publishes no output artifact. Run dry-run through the Python/CLI interface.

CWL fixes the internal `output_dir` to `output` and returns that directory as a `Directory` output. It does not accept an `output_dir` input. Python and the installed CLI require you to specify the output directory.

**Note:** Including a file means asking rasterio to read it. An empty include filter can select text files or sidecars that rasterio cannot open. Use exclusions to avoid them.

Private storage needs credentials for both object listing (`obstore`) and raster reads (rasterio/GDAL). Each library resolves credentials from the runtime environment and its supported credential providers. Configure access for both locally or on the MAAP worker; successful listing alone does not prove raster access. The image contains no storage credentials. For Docker or CWL, pass the needed credentials into the container using your environment's supported mechanism, such as Docker environment options or cwltool's `--preserve-environment`.

## Python and installed CLI

From the repository root, install the locked dependencies and run the Python entry point:

```bash
uv sync --frozen
uv run --frozen main.py \
  --source "s3://bucket/path/to/files/" \
  --output_dir /tmp/stac-output
```

The installed console command accepts the same arguments:

```bash
uv run --frozen dps-stac-item-generator \
  --source "s3://bucket/path/to/files/" \
  --output_dir /tmp/stac-output \
  --region us-west-2 \
  --include-extensions ".tif,.tiff,.nc" \
  --exclude-extensions ""
```

Use `--include-extensions ""` to include all files. For local data, set `--source` to an absolute directory URL such as `file:///tmp/input`. `--dry-run` logs the planned mapping and unmatched/filtered counts without raster reads or catalog output.

## Docker and local CWL

Release images use `ghcr.io/maap-project/dps-import-cogs:v<VERSION>`. Set `DPS_PROCESS_VERSION` to a published OGC release version without the image tag's `v` prefix. Use the CWL from that same release, since its `dockerPull` selects the matching image.

**Note:** The migration starts with metadata aligned to the existing `0.2.0` release. That does not establish that an OGC image or process for that version exists. Before publication, build a local image tagged to match the CWL's `dockerPull` rather than assuming you can pull it from GHCR.

Run the CLI in a published image with an output mount:

```bash
: "${DPS_PROCESS_VERSION:?Set a published OGC release version}"
mkdir -p output
docker run --rm \
  --mount "type=bind,source=$PWD/output,target=/output" \
  --entrypoint /app/dps-import-cogs/.venv/bin/dps-stac-item-generator \
  "ghcr.io/maap-project/dps-import-cogs:v${DPS_PROCESS_VERSION}" \
  --source "s3://bucket/path/to/files/" \
  --output_dir /output
```

For CWL, save these inputs as `local-job.yml`. `source` is a URL string, not a CWL `Directory` to stage; local `file://` sources must be accessible inside the execution container.

```yaml
source: "s3://bucket/path/to/files/"
region: us-west-2
include_extensions: ".tif,.tiff,.nc"
exclude_extensions: ""
```

Validate the package and run it with Docker available:

```bash
uvx --from cwltool cwltool --validate dps-import-cogs.cwl
uvx --from cwltool cwltool --outdir ./cwl-output \
  dps-import-cogs.cwl local-job.yml
```

## Production MAAP jobs

Use the project's development environment with production MAAP authentication. The dev dependency `maap-py>=5.1.0` provides the OGC discovery and submission API; the lockfile selects 5.1.0. It is not a runtime dependency, and the generator image excludes it with `uv sync --frozen --no-dev`. The [HLS mosaic example](https://github.com/MAAP-Project/hls-cloud-free-temporal-mosaic#archive-discovery-and-job-enumeration) uses the same discovery/submission path.

Save the example below as `submit_ogc_job.py` and run it from the repository root:

```bash
uv sync --frozen --group dev
uv run --frozen --group dev python submit_ogc_job.py
```

Set `DPS_PROCESS_VERSION` to the exact version reported for a deployed OGC release. Discover its process ID by title and version instead of deriving one from the CWL ID or the old algorithm name.

**Note:** This example submits a real job on `maap-dps-worker-8gb`. Replace the source URL and confirm the deployed version and storage access before running it.

```python
import logging
import os

from maap.maap import MAAP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
maap = MAAP(maap_host="api.maap-project.org")
process_version = os.environ["DPS_PROCESS_VERSION"]
response = maap.list_algorithms()
response.raise_for_status()
process_ids = [
    process["processID"]
    for process in response.json()["processes"]
    if process["title"] == "DPS STAC Item Generator"
    and process["version"] == process_version
]
if len(process_ids) != 1:
    raise ValueError(f"Expected one process for {process_version}, got {process_ids}")

response = maap.submit_job(
    process_id=process_ids[0],
    inputs={"source": "s3://bucket/path/to/files/"},
    queue="maap-dps-worker-8gb",
    tag="stac-import",
)
response.raise_for_status()
job_id = response.json()["jobID"]
logger.info("Submitted job %s", job_id)
```

Save `job_id` to check the job later. Rerunning submission can create duplicate jobs. Check status without resubmitting:

```python
response = maap.get_job_status(job_id)
response.raise_for_status()
logger.info("Job %s: %s", job_id, response.json()["status"])
```

## Output and visualization

The output hierarchy is **Catalog -> Item**, with no Collection layer:

```text
output/
├── catalog.json
└── <item-id>/
    └── <item-id>.json
```

Without config, each matching raster gets an Item with an `asset` pointing to its existing source URL. In grouped mode, each raster is extracted separately through `rio-stac`; projection and raster fields are retained on their own asset, while the configured reference raster supplies Item geometry and bbox. A configured non-raster attachment is represented directly as a STAC asset and is never opened as a raster. The catalog's self-contained links connect the STAC JSON files; the assets still require access to original storage.

The migrated process does not establish the old `GenerateStacItems` algorithm identity or the old username/algorithm/version/tag collection-ID pattern. Do not assume automatic DPS User STAC ingestion or construct a collection ID from those values. Check the deployed service's job results and ingestion behavior.

If MAAP ingests the results into DPS User STAC, use the collection ID returned by that service. For compatible raster assets, the existing visualization endpoints accept `assets=asset`:

- Collection: `https://dps-stac.maap-project.org/collections/{collection_id}`
- TileJSON: `https://titiler-dps-stac.maap-project.org/collections/{collection_id}/tiles/WebMercatorQuad/tilejson.json?assets=asset`
- Map: `https://titiler-dps-stac.maap-project.org/collections/{collection_id}/WebMercatorQuad/map.html?assets=asset`

Append visualization parameters such as `&colormap_name=viridis&rescale=0,100` as needed. The rendering service also needs access to the source assets.

## Local checks

Run the code tests and generate real fixtures without MAAP or remote storage. The release workflow tests also require Bash, Git, and `jq`; they fake only HTTP and polling sleeps, never contact MAAP, and check registration/update failures and polling URL safety.

```bash
uv run --frozen pytest
uv run --frozen python scripts/local_format_smoke_test.py --help
uv run --frozen python scripts/local_format_smoke_test.py
```

To exercise the actual CWL workflow and container, first build a local image tagged exactly as the current CWL's `dockerPull`, then run:

```bash
CWL_CONTAINER_TEST=1 uv run --frozen --with cwltool pytest tests/test_application_package.py
```

These opt-in tests mount tiny source rasters read-only, disable image pulls and schema downloads, and run containers with networking disabled. They verify the returned `Directory`, source asset URLs, default/empty filters, and an empty catalog. They skip during ordinary pytest runs when Docker and the matching image are not requested.

The smoke script runs the Python entry point using its current interpreter. It creates tiny GeoTIFF and COG fixtures, plus NetCDF, JPEG 2000, PNG, and JPEG when `gdal_translate` is available and HDF5 when `h5import` is available. It logs the `/tmp/dps-stac-local-*` input and output paths and leaves them for inspection. Use `--work-dir` to choose a directory. Some fixture formats lack georeferencing; rio-stac warns and uses a world bbox for those assets.

## CI, releases, and deployment

CI runs code-quality checks and Python 3.12–3.14 tests, validates the CWL application package, and tests the container. Locked Rasterio 1.4.3 has no Python 3.14 wheel, so that matrix entry builds it against Ubuntu 24.04's native GDAL 3.8.x with `build-essential` and `libgdal-dev`; local Python 3.14 testing needs equivalent GDAL headers and compiler tooling. Main-branch builds publish the `latest` image. Published releases publish version-tagged and commit-SHA-tagged images before MAAP registration. Deployment uses a commit-pinned CWL URL and polls MAAP until registration succeeds or fails; publishing an image alone does not prove deployment succeeded.

Repository administrators must configure:

- A `release-please` GitHub environment that allows the `main` branch, with no required reviewers or wait timer if releases should remain automatic. Store `RELEASE_PLEASE_TOKEN` there (or as a repository secret) with permission to create/update release PRs and publish releases. Use a dedicated PAT or GitHub App token, not `GITHUB_TOKEN`, so published releases trigger the downstream release workflow. Environment protection rules can otherwise leave release automation waiting for approval.
- `MAAP_TOKEN` in the `production` GitHub environment for production registration and deployment polling.
- GHCR pull access for MAAP workers and local users. Make the package public or provide registry credentials through the execution environment.
- `production` environment protections that allow release tags (`v*`), plus any required reviewers. The release workflow runs against a tag, so a branch-only `main` restriction blocks deployment. Deployment waits for approval when those rules require it.

Keep release metadata and image tags in sync through release automation. Configure examples with the deployed version rather than assuming the migration's starting metadata identifies a live process.
