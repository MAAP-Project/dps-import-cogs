"""Regression tests for the installed CLI and application package metadata."""

import json
import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pystac import Catalog
from rasterio.transform import from_origin
from yaml import safe_load

ROOT = Path(__file__).resolve().parents[1]


def test_application_package_versions_agree() -> None:
    """Package, lock, release baseline, and CWL all identify the same release."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == project["name"])
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text())
    cwl = safe_load((ROOT / "dps-import-cogs.cwl").read_text())
    tool = next(p for p in cwl["$graph"] if p["id"] == "main")

    assert package["version"] == project["version"] == manifest["."]
    assert version(project["name"]) == project["version"]
    assert cwl["s:softwareVersion"] == cwl["s:version"] == project["version"]
    assert tool["requirements"]["DockerRequirement"]["dockerPull"] == (
        f"ghcr.io/maap-project/dps-import-cogs:v{project['version']}"
    )


@pytest.mark.parametrize(
    ("filters", "expected_ids"),
    [
        ([], {"image"}),
        (["--include-extensions=", "--exclude-extensions="], {"image", "extra"}),
        (["--include-extensions=", "--exclude-extensions=.dat"], {"image"}),
        (["--include-extensions=.dat", "--exclude-extensions="], {"extra"}),
    ],
)
def test_installed_cli_preserves_extension_arguments(
    tmp_path: Path, filters: list[str], expected_ids: set[str]
) -> None:
    """Default, empty, and explicit filters affect the real generated catalog."""
    source = tmp_path / "source"
    source.mkdir()
    image = source / "image.tif"
    with rasterio.open(
        image,
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
    # A readable raster with an unlisted suffix distinguishes empty from default.
    (source / "extra.dat").write_bytes(image.read_bytes())

    result = subprocess.run(
        [
            str(Path(sys.executable).with_name("dps-stac-item-generator")),
            "--source",
            source.as_uri(),
            "--output_dir",
            "output",
            *filters,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    catalog = Catalog.from_file(str(tmp_path / "output" / "catalog.json"))
    items = list(catalog.get_items(recursive=True))
    assert {item.id for item in items} == expected_ids
    assert all("asset" in item.assets for item in items)
