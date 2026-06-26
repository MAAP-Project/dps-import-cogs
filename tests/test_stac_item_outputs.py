"""Characterization tests for real STAC item creation outputs."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.transform import from_origin
from rio_stac import create_stac_item

from dps_stac_item_generator.generator import media_type_for_extension


def write_geotiff(path: Path) -> None:
    """Write a tiny georeferenced GeoTIFF for STAC item characterization."""
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=1,
        width=1,
        count=1,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(-180, 90, 1, 1),
    ) as dataset:
        dataset.write(np.array([[[42]]], dtype="uint16"))


def test_real_geotiff_stac_item_shape(tmp_path: Path) -> None:
    """A real GeoTIFF produces a STAC item with expected core fields."""
    source = tmp_path / "asset.tif"
    write_geotiff(source)

    item = create_stac_item(
        source=str(source),
        id="asset",
        with_proj=True,
        with_raster=True,
        asset_media_type=media_type_for_extension(".tif"),
    )

    item_dict = item.to_dict()

    assert item_dict["type"] == "Feature"
    assert item_dict["stac_version"]
    assert item_dict["id"] == "asset"
    assert item_dict["geometry"]["type"] == "Polygon"
    assert item_dict["bbox"] == [-180.0, 89.0, -179.0, 90.0]
    assert item_dict["properties"]["proj:epsg"] == 4326
    assert item_dict["assets"]["asset"]["href"] == str(source)
    assert item_dict["assets"]["asset"]["type"] == "image/tiff; application=geotiff"
    assert item_dict["assets"]["asset"]["raster:bands"][0]["data_type"] == "uint16"


def test_text_file_stac_item_creation_fails(tmp_path: Path) -> None:
    """rio-stac cannot create raster metadata for a plain text file."""
    source = tmp_path / "notes.txt"
    source.write_text("hello\n")

    with pytest.raises(
        RasterioIOError, match="not recognized as being in a supported file format"
    ):
        create_stac_item(
            source=str(source),
            id="notes",
            asset_media_type="text/plain",
        )
