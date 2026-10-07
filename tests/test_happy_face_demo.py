"""Behavior tests for the self-contained happy-face DPS workflow."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pystac import Catalog
from pystac.media_type import MediaType
from rasterio.transform import Affine, from_origin
from rio_cogeo.cogeo import cog_validate
from yaml import safe_load

from dps_stac_item_generator import generator, happy_face

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_happy_face.py"


def generate_demo(output_dir: Path, size: int = 64) -> None:
    """Run the raster generator CLI with a deterministic small size."""
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
    transforms: dict[str, Affine] = {}
    for path in paths:
        tile = path.parent.name
        channel = path.stem
        valid, errors, warnings = cog_validate(path)
        assert valid, f"Invalid COG {path}: {errors}; warnings: {warnings}"
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
    assert rgb[0, 32, 63] == 255 and rgb[0, 32, 64] == 255
    smile_pixels = (rgb[0] == 185) & (rgb[1] == 25) & (rgb[2] == 65)
    assert smile_pixels[44, 63] and smile_pixels[44, 64]
    center_rows = np.flatnonzero(smile_pixels[:, 63])
    corner_rows = np.flatnonzero(smile_pixels[:, 43])
    assert center_rows.mean() > corner_rows.mean()


def test_happy_face_config_catalogs_generated_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The existing RGB config still groups generator output through generator.run."""
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
        assert item.datetime is not None
        assert item.datetime.isoformat() == "2026-01-01T00:00:00+00:00"
        assert all(
            asset.extra_fields["raster:bands"][0]["data_type"] == "uint8"
            for asset in item.assets.values()
        )
        assert all(asset.media_type == MediaType.COG for asset in item.assets.values())


def test_happy_face_workflow_bundles_cogs_and_relocates(
    tmp_path: Path,
) -> None:
    """Returned catalog assets resolve to generated COGs after output relocation."""
    output = tmp_path / "output"
    happy_face.run(output, size=64)
    assert not list(tmp_path.glob(".output.happy-face-*"))

    catalog_path = output / "catalog.json"
    catalog = Catalog.from_file(str(catalog_path))
    items = {item.id: item for item in catalog.get_items(recursive=True)}
    assert set(items) == {"happy-face-left", "happy-face-right"}
    asset_basenames = []
    for item in items.values():
        assert set(item.assets) == {"red", "green", "blue"}
        assert item.datetime is not None
        assert item.datetime.isoformat() == "2026-01-01T00:00:00+00:00"
        for asset in item.assets.values():
            assert asset.media_type == MediaType.COG
            assert not Path(asset.href).is_absolute()
            raster_path = (Path(item.get_self_href()).parent / asset.href).resolve()
            assert raster_path.is_relative_to(output.resolve())
            assert raster_path.is_file()
            asset_basenames.append(raster_path.name)
            valid, errors, warnings = cog_validate(raster_path)
            assert valid, f"Invalid COG {raster_path}: {errors}; warnings: {warnings}"
            with rasterio.open(raster_path) as dataset:
                assert dataset.count == 1
                assert dataset.width == dataset.height == 64
                assert dataset.driver == "GTiff"

    # stage_out.py maps by basename first. Unique basenames ensure its summary
    # map selects the corresponding bundled raster rather than a sibling asset.
    assert len(asset_basenames) == len(set(asset_basenames)) == 6
    summary_file_map = {
        path.name: str(path.resolve()) for path in output.rglob("*.tif")
    }
    for item in items.values():
        item_dir = Path(item.get_self_href()).parent
        for asset in item.assets.values():
            # stage_out.py prefers its basename-keyed cwltool map; the unique
            # names must map to the same file the relative href identifies.
            mapped_path = Path(summary_file_map[Path(asset.href).name])
            href_path = (item_dir / asset.href).resolve()
            assert mapped_path == href_path
            # Its fallback and relpath round-trip also preserve hrefs in place.
            actual_path = os.path.abspath(os.path.join(item_dir, asset.href))
            assert os.path.relpath(actual_path, item_dir) == asset.href
            assert mapped_path.is_file()

    relocated = tmp_path / "moved-output"
    shutil.copytree(output, relocated)
    moved_catalog = Catalog.from_file(str(relocated / "catalog.json"))
    moved_items = list(moved_catalog.get_items(recursive=True))
    assert len(moved_items) == 2
    for item in moved_items:
        for asset in item.assets.values():
            raster_path = (Path(item.get_self_href()).parent / asset.href).resolve()
            assert raster_path.is_relative_to(relocated.resolve())
            with rasterio.open(raster_path) as dataset:
                assert dataset.count == 1


def test_happy_face_cwl_is_a_fileless_directory_workflow() -> None:
    """Dedicated CWL package has a distinct identity and requires no staged files."""
    cwl = safe_load((ROOT / "happy-face-demo.cwl").read_text())
    workflow = next(node for node in cwl["$graph"] if node["class"] == "Workflow")
    tool = next(node for node in cwl["$graph"] if node["class"] == "CommandLineTool")

    assert workflow["id"] == "generate_happy_face_demo"
    assert workflow["label"] == "Self-contained Happy Face DPS Demo"
    assert workflow["inputs"] == {}
    assert workflow["outputs"]["output"]["type"] == "Directory"
    assert tool["inputs"] == {}
    assert tool["outputs"]["output"]["type"] == "Directory"
    assert tool["requirements"]["DockerRequirement"]["dockerPull"] == (
        "ghcr.io/maap-project/dps-import-cogs:happy-face-demo-v0.1.0"
    )
    assert json.loads(json.dumps(cwl))["s:version"] == "0.1.0"
