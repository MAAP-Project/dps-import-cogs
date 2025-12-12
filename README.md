# DPS Import COGs

Create STAC items for raster files in object storage

## About

This DPS algorithm creates STAC metadata for existing raster files (GeoTIFFs) stored in object storage (S3, Azure, GCS, etc.). The workflow:

1. Lists all files at the specified source location
2. Filters for `.tif` files
3. Creates a STAC item for each raster using `rio-stac`
4. Exports a self-contained STAC catalog with all items

This tool is useful for importing existing COG (Cloud Optimized GeoTIFF) datasets into STAC format for better discoverability and interoperability.

## Usage

### Direct Python Invocation

```bash
uv run main.py \
  --source "s3://bucket/path/to/files/" \
  --output_dir "/tmp/output" \
  --region "us-west-2"
```

### Parameters

- `--source`: Source location of the files for which you want to generate STAC items (e.g., `s3://bucket/path/to/files/`)
- `--output_dir`: Directory where the STAC catalog will be saved
- `--region`: AWS region where the storage container exists (default: `us-west-2`)

## Output

The tool generates a self-contained STAC catalog in the output directory containing:

- A `catalog.json` file with metadata about the collection
- Individual STAC item JSON files for each raster
- Each STAC item includes projection (`proj`) and raster band information
