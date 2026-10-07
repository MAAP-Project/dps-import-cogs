"""Behavior tests for the generated happy-face GeoTIFF demo."""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pystac import Catalog
from rasterio.transform import from_origin

from dps_stac_item_generator import generator

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_happy_face.py"


def generate_demo(output_dir: Path, size: int = 64) -> None:
    """Run the user-facing generator CLI with a deterministic small size."""
    subprocess.run(
        [sys.executable, str(SCRIPT), str(output_dir), "--size", str(size)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_generated_tiles_are_adjacent_and_channels_form_one_image(
    tmp_path: Path,
) -> None:
    """Six matching channel rasters have adjacent transforms and a continuous face."""
    source = tmp_path / "rasters"
    generate_demo(source)
    paths = sorted(source.glob("*/*.tif"))
    assert len(paths) == 6

    arrays: dict[str, dict[str, np.ndarray]] = {"left": {}, "right": {}}
    transforms = {}
    for path in paths:
        tile = path.parent.name
        channel = path.stem
        with rasterio.open(path) as dataset:
            assert dataset.count == 1
            assert dataset.dtypes == ("uint8",)
            assert dataset.crs.to_string() == "EPSG:3857"
            assert dataset.nodata is None
            assert dataset.descriptions == (channel,)
            assert dataset.width == dataset.height == 64
            arrays[tile][channel] = dataset.read(1)
            transforms.setdefault(tile, dataset.transform)
            assert dataset.transform == transforms[tile]

    assert transforms["left"] == from_origin(-6400, 6400, 100, 100)
    assert transforms["right"] == from_origin(0, 6400, 100, 100)
    with (
        rasterio.open(source / "left/red.tif") as left,
        rasterio.open(source / "right/red.tif") as right,
    ):
        assert left.bounds.right == right.bounds.left

    rgb = np.concatenate(
        [
            np.stack([arrays[tile][key] for key in ("red", "green", "blue")])
            for tile in ("left", "right")
        ],
        axis=2,
    )
    assert not np.array_equal(rgb[0], rgb[1])
    assert not np.array_equal(rgb[1], rgb[2])
    # The center seam crosses the warm face and its continuous curved smile.
    assert rgb[0, 32, 63] == 255 and rgb[0, 32, 64] == 255
    assert rgb[0, 41, 63] == 185 and rgb[0, 41, 64] == 185


def test_happy_face_config_catalogs_two_items_with_three_real_assets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The shipped grouping config catalogs the generated rasters via generator.run."""
    source = tmp_path / "rasters"
    generate_demo(source)
    paths = [path.relative_to(source).as_posix() for path in source.glob("*/*.tif")]
    monkeypatch.setattr(generator, "from_url", lambda *_args, **_kwargs: "fake-store")
    monkeypatch.setattr(
        generator.obstore,
        "list",
        lambda _store: [[{"path": path} for path in paths]],
    )

    output = tmp_path / "catalog"
    generator.run(
        source=source.as_uri(),
        output_dir=output,
        config_path=ROOT / "examples" / "happy-face.json",
    )
    items = {
        item.id: item
        for item in Catalog.from_file(str(output / "catalog.json")).get_items()
    }
    assert set(items) == {"happy-face-left", "happy-face-right"}
    for item in items.values():
        assert set(item.assets) == {"red", "green", "blue"}
        assert item.datetime.isoformat() == "2026-01-01T00:00:00+00:00"
        assert all(
            asset.href.endswith(f"/{item.id.removeprefix('happy-face-')}/{key}.tif")
            for key, asset in item.assets.items()
        )
        assert all(
            asset.extra_fields["raster:bands"][0]["data_type"] == "uint8"
            for asset in item.assets.values()
        )
