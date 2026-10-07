"""Public workflow tests for configurable and deterministic catalog planning."""

import json
import logging
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pystac import Catalog
from rasterio.errors import RasterioIOError
from rasterio.transform import from_origin

from dps_stac_item_generator import generator

ROOT = Path(__file__).resolve().parents[1]


def write_raster(path: Path, *, width: int = 2, crs: str = "EPSG:4326") -> None:
    """Write a tiny real raster fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=1,
        width=width,
        count=1,
        dtype="uint16",
        crs=crs,
        transform=from_origin(0, 1, 1, 1),
    ) as dataset:
        dataset.write(np.ones((1, 1, width), dtype="uint16"))


def install_listing(monkeypatch: pytest.MonkeyPatch, paths: list[str]) -> None:
    """Use a small deterministic fake at the object-listing boundary."""
    monkeypatch.setattr(generator, "from_url", lambda *_args, **_kwargs: "fake-store")
    monkeypatch.setattr(
        generator.obstore,
        "list",
        lambda _store: [[{"path": path} for path in paths]],
    )


def test_default_ids_are_stable_and_separate_same_basenames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """IDs include full source URLs and do not depend on listing order."""
    source = tmp_path / "source"
    paths = ["a/same.tif", "b/same.tif", "a/same.nc"]
    for path in paths:
        write_raster(source / path)
    install_listing(monkeypatch, paths)
    monkeypatch.setattr(generator, "is_cloud_optimized_geotiff", lambda _href: False)
    ids: list[set[str]] = []
    for index, listing in enumerate((paths, list(reversed(paths)))):
        monkeypatch.setattr(
            generator.obstore,
            "list",
            lambda _store, listing=listing: [[{"path": path} for path in listing]],
        )
        output = tmp_path / f"out-{index}"
        generator.run(
            source=source.as_uri(), output_dir=output, include_extensions=".tif,.nc"
        )
        catalog = Catalog.from_file(str(output / "catalog.json"))
        items = list(catalog.get_items())
        assert len(items) == 3
        assert all(item.assets["asset"] for item in items)
        ids.append({item.id for item in items})
    assert ids[0] == ids[1]


def test_grouped_items_keep_per_asset_projection_and_attachment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Grouped assets retain separate raster extensions; thumbnails stay non-raster."""
    source = tmp_path / "source"
    paths = [
        "32TPR/2026-01-01/source-A/gamma0_hh.tif",
        "32TPR/2026-01-01/source-A/gamma0_hv.tif",
        "32TPR/2026-01-01/source-A/thumbnail.png",
        "33UUU/2026-01-01/source-A/gamma0_hh.tif",
        "33UUU/2026-01-01/source-A/gamma0_hv.tif",
        "33UUU/2026-01-01/source-A/thumbnail.png",
    ]
    for path in paths:
        if path.endswith(".tif"):
            write_raster(
                source / path, crs="EPSG:4326" if "hh" in path else "EPSG:3857"
            )
        else:
            (source / path).parent.mkdir(parents=True, exist_ok=True)
            (source / path).write_bytes(b"not a raster")
    install_listing(monkeypatch, paths)
    monkeypatch.setattr(generator, "is_cloud_optimized_geotiff", lambda _href: False)
    output = tmp_path / "catalog"
    generator.run(
        source=source.as_uri(),
        output_dir=output,
        config_path=ROOT / "examples/gamma0-grouped.json",
    )
    items = {
        item.id: item
        for item in Catalog.from_file(str(output / "catalog.json")).get_items()
    }
    assert set(items) == {
        "biomass-source-A-32TPR-2026-01-01",
        "biomass-source-A-33UUU-2026-01-01",
    }
    item = items["biomass-source-A-32TPR-2026-01-01"]
    assert set(item.assets) == {"hh", "hv", "thumbnail"}
    assert item.assets["thumbnail"].media_type == "image/png"
    assert item.assets["thumbnail"].roles == ["thumbnail"]
    assert "proj:epsg" not in item.properties
    item_document = json.loads((output / item.id / f"{item.id}.json").read_text())
    assert item_document["assets"]["hh"]["proj:epsg"] == 4326
    assert item_document["assets"]["hv"]["proj:epsg"] == 3857
    assert item_document["assets"]["hv"]["raster:bands"][0]["data_type"] == "uint16"


def test_plan_errors_and_dry_run_precede_raster_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Missing grouped assets fail before metadata reads; dry-run only reports plan."""
    paths = ["32TPR/2026-01-01/source-A/gamma0_hh.tif"]
    install_listing(monkeypatch, paths)
    monkeypatch.setattr(
        generator, "create_stac_item", lambda **_kwargs: pytest.fail("raster opened")
    )
    with pytest.raises(ValueError, match="missing required asset"):
        generator.run(
            source="s3://bucket/input",
            output_dir=tmp_path / "out",
            config_path=ROOT / "examples/gamma0-grouped.json",
        )
    assert not (tmp_path / "out").exists()
    caplog.set_level(logging.INFO)
    generator.run(
        source="s3://bucket/input",
        output_dir=tmp_path / "dry",
        include_extensions=".tif",
        dry_run=True,
    )
    assert "Plan: 1 item(s), 0 unmatched, 0 filtered" in caplog.text
    assert not (tmp_path / "dry").exists()


def test_extension_filtered_file_is_never_opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An excluded sidecar is not sent to rio-stac metadata extraction."""
    source = tmp_path / "source"
    write_raster(source / "selected.tif")
    (source / "notes.txt").write_text("not raster metadata")
    install_listing(monkeypatch, ["selected.tif", "notes.txt"])
    monkeypatch.setattr(generator, "is_cloud_optimized_geotiff", lambda _href: False)
    output = tmp_path / "out"
    generator.run(source=source.as_uri(), output_dir=output, include_extensions=".tif")
    items = list(Catalog.from_file(str(output / "catalog.json")).get_items())
    assert len(items) == 1
    assert items[0].assets["asset"].href.endswith("selected.tif")


def test_failed_raster_read_leaves_published_catalog_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A raster failure before publication preserves the existing output."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "broken.tif").write_text("not a raster")
    install_listing(monkeypatch, ["broken.tif"])
    output = tmp_path / "out"
    output.mkdir()
    existing = output / "keep.txt"
    existing.write_text("published")
    with pytest.raises(RasterioIOError):
        generator.run(source=source.as_uri(), output_dir=output)
    assert existing.read_text() == "published"
    assert not (output / "catalog.json").exists()


def test_invalid_config_is_rejected_before_listing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Config schema errors are caught before creating a store or listing."""
    config = tmp_path / "bad.json"
    config.write_text(json.dumps({"path_pattern": "(?P<x>.*)", "unrecognized": True}))
    monkeypatch.setattr(
        generator, "from_url", lambda *_args, **_kwargs: pytest.fail("store opened")
    )
    with pytest.raises(ValueError, match="Unknown config field"):
        generator.run(
            source="s3://bucket/input", output_dir=tmp_path / "out", config_path=config
        )


@pytest.mark.parametrize(
    ("config_name", "paths"),
    [
        ("directory-per-item.json", ["32TPR/red.tif", "32TPR/nir.tif"]),
        ("filename-grouped.json", ["scene-1_red.tif", "scene-1_nir.tif"]),
        (
            "gamma0-grouped.json",
            [
                "32TPR/2026-01-01/source-A/gamma0_hh.tif",
                "32TPR/2026-01-01/source-A/gamma0_hv.tif",
                "32TPR/2026-01-01/source-A/thumbnail.png",
            ],
        ),
    ],
)
def test_shipped_group_configs_match_documented_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_name: str,
    paths: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every shipped grouping config produces its documented mapping in dry-run."""
    install_listing(monkeypatch, paths)
    caplog.set_level(logging.INFO)
    generator.run(
        source="s3://bucket/input",
        output_dir=tmp_path / "out",
        config_path=ROOT / "examples" / config_name,
        dry_run=True,
    )
    assert "Plan: 1 item(s), 0 unmatched, 0 filtered" in caplog.text
    assert not (tmp_path / "out").exists()
