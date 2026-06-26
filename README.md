# DPS STAC Item Generator

Create STAC items for selected files in object storage.

## About

This DPS algorithm creates STAC metadata for existing files stored in object storage (S3, Azure, GCS, etc.). The workflow:

1. Lists all files at the specified source location
2. Filters files by configurable include/exclude extension lists
3. Creates a STAC item for each matching asset using `rio-stac`
4. Exports a self-contained STAC catalog with all items

By default, the algorithm includes GeoTIFF (`.tif`, `.tiff`) and NetCDF (`.nc`) files. This tool is useful for importing existing geospatial datasets into STAC format for better discoverability and interoperability.
The STAC items will be uploaded to the DPS User STAC in a collection associated with your username, the algorithm name/version, and the job tag.

## Usage


### MAAP DPS

To run the algorithm via DPS, you can follow this example. The only required parameter is `source` which describes the storage location of the files for which you want to generate STAC metadata.

```python
from maap.maap import MAAP

maap = MAAP(maap_host="api.maap-project.org")

job = maap.submitJob(
    algo_id="GenerateStacItems",
    version="v0.1",
    identifier="test-run",
    queue="maap-dps-worker-8gb",
    source="s3://nasa-maap-data-store/file-staging/nasa-map/glad-glclu2020/v2/2020/",
)

```

Each job will produce a STAC item for each file under the provided `source` whose extension matches the configured filters. The STAC items will be uploaded to the DPS User STAC catalog automatically after job completion. All jobs associated with the same algorithm, version, username, and job tag/identifier will be added to the same collection with the following format:

`{username}__GenerateStacItems__v0.1__{identifier}`


You can access the items following this pattern:
```
https://mxyjvl46y3.execute-api.us-west-2.amazonaws.com/{collection_id}
```

where `identifier` is the value you provided for the job identifier/tag when you submitted the job.

The job results can be visualized using the DPS User STAC titiler endpoint:

* tilejson: `https://ansdoe39vf.execute-api.us-west-2.amazonaws.com/collections/{collection_id}/tiles/WebMercatorQuad/tilejson.json?assets=asset`

* quick map: `https://ansdoe39vf.execute-api.us-west-2.amazonaws.com/collections/{collection_id}/WebMercatorQuad/map.html?assets=asset`

To customize the visualization, you can add all of the familiar visualization parameters to the end of the url like `&colormap_name=viridis&rescale=0,100`

### Direct Python Invocation

```bash
uv run main.py \
  --source "s3://bucket/path/to/files/" \
  --output_dir "/tmp/output" \
  --region "us-west-2" \
  --include-extensions ".tif,.tiff,.nc" \
  --exclude-extensions ""
```

### Parameters

- `--source`: Source location of the files for which you want to generate STAC items (e.g., `s3://bucket/path/to/files/`)
- `--output_dir`: Directory where the STAC catalog will be saved
- `--region`: AWS region where the storage container exists (default: `us-west-2`)
- `--include-extensions`: Comma-separated extensions to include (default: `.tif,.tiff,.nc`). Use an empty string to include all files.
- `--exclude-extensions`: Comma-separated extensions to exclude. Exclusions override inclusions.

## Output

The tool generates a self-contained STAC catalog in the output directory containing:

- A `catalog.json` file with metadata about the collection
- Individual STAC item JSON files for each matching asset
- Each STAC item includes projection (`proj`) and raster band information when `rio-stac` can derive it from the source asset
