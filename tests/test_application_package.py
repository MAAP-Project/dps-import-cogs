"""Regression tests for the installed CLI and application package metadata."""

import json
import os
import shlex
import shutil
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


@pytest.fixture
def raster_source(tmp_path: Path) -> Path:
    """Create readable rasters with a default suffix and an unlisted suffix."""
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
    return source


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
    tmp_path: Path, raster_source: Path, filters: list[str], expected_ids: set[str]
) -> None:
    """Default, empty, and explicit filters affect the real generated catalog."""
    source = raster_source
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
    assert {
        Path(item.assets["asset"].href).stem.split(".")[0] for item in items
    } == expected_ids
    assert len({item.id for item in items}) == len(items)
    for item in items:
        asset_href = item.assets["asset"].href
        assert asset_href in {
            (source / "image.tif").as_uri(),
            (source / "extra.dat").as_uri(),
        }
        assert item.id.startswith(Path(asset_href).stem + "-")
    assert not list((tmp_path / "output").rglob("*.tif"))


@pytest.mark.skipif(
    os.environ.get("CWL_CONTAINER_TEST") != "1",
    reason="Opt-in check requires cwltool, Docker, and the locally built release image",
)
@pytest.mark.parametrize(
    ("filters", "expected_ids"),
    [
        ({}, {"image"}),
        ({"include_extensions": "", "exclude_extensions": ""}, {"image", "extra"}),
        ({"include_extensions": "", "exclude_extensions": ".dat"}, {"image"}),
        ({"include_extensions": ".tif", "exclude_extensions": ".tif"}, set()),
    ],
)
def test_cwl_container_returns_catalog_offline(
    tmp_path: Path,
    raster_source: Path,
    filters: dict[str, str],
    expected_ids: set[str],
) -> None:
    """Execute the unmodified workflow offline with mounted real source rasters."""
    docker = shutil.which("docker")
    cwltool = shutil.which("cwltool")
    assert docker and cwltool, "Install Docker and run pytest with --with cwltool"
    # source is intentionally a URL string, not a staged CWL Directory. Add a
    # read-only fixture mount while leaving cwltool's container invocation intact.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "docker"
    mount = f"type=bind,source={raster_source},target={raster_source},readonly"
    wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = run ]; then\n'
        "  shift\n"
        f'  exec {shlex.quote(docker)} run --mount {shlex.quote(mount)} "$@"\n'
        "fi\n"
        f'exec {shlex.quote(docker)} "$@"\n'
    )
    wrapper.chmod(0o755)
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"source": raster_source.as_uri(), **filters}))
    result = subprocess.run(
        [
            cwltool,
            "--skip-schemas",
            "--disable-pull",
            "--custom-net",
            "none",
            "--outdir",
            str(tmp_path / "result"),
            str(ROOT / "dps-import-cogs.cwl"),
            str(job),
        ],
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)["output"]
    assert output["class"] == "Directory"
    catalog_path = Path(output["path"]) / "catalog.json"
    catalog = Catalog.from_file(str(catalog_path))
    assert list(catalog.get_children()) == []
    items = list(catalog.get_items())
    assert {
        Path(item.assets["asset"].href).stem.split(".")[0] for item in items
    } == expected_ids
    assert len(list(catalog_path.parent.rglob("*.json"))) == len(items) + 1
    assert not list(catalog_path.parent.rglob("*.tif"))
    for item in items:
        asset_href = item.assets["asset"].href
        assert asset_href in {
            (raster_source / "image.tif").as_uri(),
            (raster_source / "extra.dat").as_uri(),
        }
        assert item.id.startswith(Path(asset_href).stem + "-")
        assert item.bbox == [-180.0, 89.0, -179.0, 90.0]
