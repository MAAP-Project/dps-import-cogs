"""Regression tests for preserving canonical remote raster asset hrefs."""

import json
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pytest
import rasterio
from pystac import Catalog
from rasterio.transform import from_origin
from rio_stac import create_stac_item

from dps_stac_item_generator import generator


def write_raster(path: Path) -> None:
    """Write a tiny real GeoTIFF used for rio-stac metadata extraction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=1,
        width=1,
        count=1,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(0, 1, 1, 1),
    ) as dataset:
        dataset.write(np.ones((1, 1, 1), dtype="uint16"))


@pytest.mark.parametrize("grouped", [False, True], ids=["default", "grouped"])
def test_catalog_publication_preserves_canonical_s3_asset_hrefs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, grouped: bool
) -> None:
    """Raster hrefs survive rio-stac creation and PySTAC href resolution unchanged."""
    source = "s3://maap-ops-workspace/shared/henrydevseed/happy-face"
    relative_paths = ["right/red.tif"]
    keys = ["asset"]
    config_json = None
    if grouped:
        relative_paths = [
            "right/red.tif",
            "right/green.tif",
            "right/blue.tif",
        ]
        keys = ["red", "green", "blue"]
        config_json = json.dumps(
            {
                "path_pattern": r"right/(?P<color>red|green|blue)\.tif",
                "item_id_template": "happy-face-right",
                "asset_key_template": "{color}",
                "datetime_template": "2026-01-01T00:00:00Z",
                "reference_asset": "red",
                "required_assets": keys,
            }
        )

    local_sources = {}
    for relative_path in relative_paths:
        local_path = tmp_path / "rasters" / relative_path
        write_raster(local_path)
        local_sources[f"{source}/{relative_path}"] = local_path

    monkeypatch.setattr(generator, "from_url", lambda *_args, **_kwargs: "fake-store")
    monkeypatch.setattr(
        generator.obstore,
        "list",
        lambda _store: [[{"path": path} for path in relative_paths]],
    )
    monkeypatch.setattr(generator, "is_cloud_optimized_geotiff", lambda _href: False)

    def create_from_local_raster(**kwargs):
        # The dataset name is a local path, deliberately unlike its canonical S3 URL.
        with rasterio.open(local_sources[kwargs["source"]]) as dataset:
            return create_stac_item(
                source=dataset,
                **{key: value for key, value in kwargs.items() if key != "source"},
            )

    monkeypatch.setattr(generator, "create_stac_item", create_from_local_raster)
    output = tmp_path / "catalog"
    generator.run(
        source=source,
        output_dir=output,
        config_json=config_json,
    )

    catalog = Catalog.from_file(str(output / "catalog.json"))
    catalog.make_all_asset_hrefs_absolute()
    items = list(catalog.get_items())
    assert len(items) == 1
    assert set(items[0].assets) == set(keys)
    for key, relative_path in zip(keys, relative_paths, strict=True):
        expected_href = f"{source}/{relative_path}"
        assert items[0].assets[key].href == expected_href
        assert urlsplit(items[0].assets[key].href).scheme == "s3"
        assert items[0].assets[key].href.startswith("s3://")
