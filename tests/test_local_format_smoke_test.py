"""Exercise the local smoke script through its public command-line interface."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pystac import Catalog, MediaType
from pystac.extensions.projection import ProjectionExtension

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "local_format_smoke_test.py"


def test_smoke_script_help_and_removed_runner_option() -> None:
    """The script offers Python-only execution and rejects the removed option."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--work-dir" in result.stdout
    assert "--runner" not in result.stdout

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--runner", "run-sh"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: --runner run-sh" in result.stderr


@pytest.mark.parametrize(
    ("include_extensions", "exclude_extensions", "expected_count"),
    [(".tif", "", 2), ("", ".txt", 2), (".tif", ".tif", 0)],
)
def test_smoke_script_generates_real_catalog_without_optional_tools(
    tmp_path: Path,
    include_extensions: str,
    exclude_extensions: str,
    expected_count: int,
) -> None:
    """Real GeoTIFF fixtures exercise filters and Catalog-to-Item export."""
    # An empty PATH models a machine without GDAL/HDF5 command-line tools.
    # Both Python processes still use the active interpreter's absolute path.
    environment = {**os.environ, "PATH": ""}
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--work-dir",
            str(tmp_path),
            f"--include-extensions={include_extensions}",
            f"--exclude-extensions={exclude_extensions}",
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "gdal_translate is not installed" in result.stderr
    assert "h5import is not installed" in result.stderr
    assert (tmp_path / "input" / "sample-geotiff.tif").is_file()
    assert (tmp_path / "input" / "sample-cog.tif").is_file()
    assert (tmp_path / "input" / "skip-me.txt").is_file()

    output_dir = tmp_path / "output"
    catalog = Catalog.from_file(str(output_dir / "catalog.json"))
    assert list(catalog.get_children()) == []
    items = list(catalog.get_items())
    assert len(items) == expected_count
    assert len(list(output_dir.rglob("*.json"))) == expected_count + 1
    assert not list(output_dir.rglob("*.tif"))
    if expected_count:
        assert {item.assets["asset"].href for item in items} == {
            (tmp_path / "input" / name).as_uri()
            for name in ("sample-geotiff.tif", "sample-cog.tif")
        }
        assert all(
            item.id.startswith(Path(item.assets["asset"].href).stem + "-")
            for item in items
        )
    for item in items:
        asset = item.assets["asset"]
        assert asset.href in {
            (tmp_path / "input" / "sample-geotiff.tif").as_uri(),
            (tmp_path / "input" / "sample-cog.tif").as_uri(),
        }
        # A tiny GTiff can also satisfy COG validation.
        assert asset.media_type in {MediaType.COG, MediaType.GEOTIFF}
        if Path(asset.href).stem == "sample-cog":
            assert asset.media_type == MediaType.COG
        assert item.bbox == [-180.0, 82.0, -172.0, 90.0]
        assert ProjectionExtension.ext(item).epsg == 4326
        assert asset.extra_fields["raster:bands"][0]["data_type"] == "uint16"
