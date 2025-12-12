"""Create STAC items for all raster files in object storage that match a prefix"""

import argparse
import logging
import os
from pathlib import Path

import obstore
from obstore.store import from_url
from pystac import Catalog, CatalogType, MediaType
from rio_cogeo.cogeo import cog_validate
from rio_stac import create_stac_item

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logging.getLogger("botocore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

DEFAULT_REGION = "us-west-2"


def run(
    source: str,
    output_dir: Path,
    region: str | None = None,
):
    source_store = from_url(source, region=region or DEFAULT_REGION)

    catalog = Catalog(
        id="DPS",
        description="DPS",
        catalog_type=CatalogType.SELF_CONTAINED,
    )

    stream = obstore.list(source_store)
    for batch in stream:
        for obj in batch:
            obj_key = os.path.join(source, obj["path"])
            if not obj_key.endswith(".tif"):
                logging.info(f"skipping {obj_key} because it is not a .tif")
                continue

            logging.info(f"processing {obj_key}")
            is_cog = cog_validate(obj_key)

            item = create_stac_item(
                source=obj_key,
                id=obj["path"].replace(".tif", ""),
                with_proj=True,
                with_raster=True,
                asset_media_type=MediaType.COG if is_cog else MediaType.GEOTIFF,
            )

            catalog.add_item(item)

    catalog.normalize_and_save(
        root_href=str(output_dir),
        catalog_type=CatalogType.SELF_CONTAINED,
    )


if __name__ == "__main__":
    parse = argparse.ArgumentParser(
        description="Queries the HLS STAC geoparquet archive and writes the result to a file"
    )
    parse.add_argument(
        "--source",
        help="Source location of the files for which you want to generate STAC items."
        " e.g. 's3://bucket/path/to/files/'",
        required=True,
    )
    parse.add_argument(
        "--output_dir", help="Directory in which to save output", required=True
    )
    parse.add_argument(
        "--region",
        help="region in which the storage container exists. e.g. 'us-west-2'",
        default="us-west-2",
    )
    args = parse.parse_args()

    output_dir = Path(args.output_dir)
    run(
        source=args.source,
        output_dir=output_dir,
    )
