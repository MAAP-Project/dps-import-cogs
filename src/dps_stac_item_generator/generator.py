"""Generate STAC items for files in object storage."""

import logging
import os
from pathlib import Path
from typing import Iterable

import obstore
from obstore.store import from_url
from pystac import Catalog, CatalogType, MediaType
from rio_cogeo.cogeo import cog_validate
from rio_stac import create_stac_item

logger = logging.getLogger(__name__)

DEFAULT_REGION = "us-west-2"
DEFAULT_INCLUDE_EXTENSIONS = (".tif", ".tiff", ".nc")
_EXTENSION_MEDIA_TYPES = {
    ".tif": MediaType.GEOTIFF,
    ".tiff": MediaType.GEOTIFF,
    ".nc": MediaType.NETCDF,
}


def normalize_extensions(extensions: str | Iterable[str] | None) -> tuple[str, ...]:
    """Normalize file extensions to lowercase dotted suffixes."""
    if extensions is None:
        return ()

    raw_extensions: Iterable[str]
    if isinstance(extensions, str):
        raw_extensions = extensions.split(",")
    else:
        raw_extensions = extensions

    normalized = []
    for extension in raw_extensions:
        extension = extension.strip().lower()
        if not extension:
            continue
        if not extension.startswith("."):
            extension = f".{extension}"
        normalized.append(extension)

    return tuple(dict.fromkeys(normalized))


def should_include_file(
    path: str,
    include_extensions: Iterable[str],
    exclude_extensions: Iterable[str] = (),
) -> bool:
    """Return whether a file path passes extension include/exclude filters."""
    suffix = Path(path).suffix.lower()
    exclude_extensions = tuple(exclude_extensions)
    if suffix in exclude_extensions:
        return False

    include_extensions = tuple(include_extensions)
    return not include_extensions or suffix in include_extensions


def media_type_for_extension(
    extension: str, *, is_cog: bool = False
) -> MediaType | str:
    """Return the STAC asset media type for a normalized file extension."""
    if extension in {".tif", ".tiff"} and is_cog:
        return MediaType.COG

    return _EXTENSION_MEDIA_TYPES.get(extension, "application/octet-stream")


def is_cloud_optimized_geotiff(source: str) -> bool:
    """Return whether a GeoTIFF source is a valid Cloud Optimized GeoTIFF."""
    result = cog_validate(source)
    if isinstance(result, tuple):
        return bool(result[0])
    return bool(result)


def create_item_id(path: str) -> str:
    """Create a STAC item ID from an object path by removing one file suffix."""
    return str(Path(path).with_suffix(""))


def run(
    source: str,
    output_dir: Path,
    region: str | None = None,
    include_extensions: str | Iterable[str] | None = DEFAULT_INCLUDE_EXTENSIONS,
    exclude_extensions: str | Iterable[str] | None = None,
) -> None:
    """Generate a self-contained STAC catalog for matching files under a source URL."""
    normalized_include_extensions = normalize_extensions(include_extensions)
    normalized_exclude_extensions = normalize_extensions(exclude_extensions)
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
            if not should_include_file(
                obj_key,
                normalized_include_extensions,
                normalized_exclude_extensions,
            ):
                logger.info(
                    "skipping %s because it did not match file filters", obj_key
                )
                continue

            logger.info("processing %s", obj_key)
            suffix = Path(obj_key).suffix.lower()
            is_cog = suffix in {".tif", ".tiff"} and is_cloud_optimized_geotiff(obj_key)

            item = create_stac_item(
                source=obj_key,
                id=create_item_id(obj["path"]),
                with_proj=True,
                with_raster=True,
                asset_media_type=media_type_for_extension(suffix, is_cog=is_cog),
            )

            catalog.add_item(item)

    catalog.normalize_and_save(
        root_href=str(output_dir),
        catalog_type=CatalogType.SELF_CONTAINED,
    )
