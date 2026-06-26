"""Generate local raster fixtures and run the STAC item generator against them."""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

LOGGER = logging.getLogger(__name__)
DEFAULT_EXTENSIONS = ".tif,.tiff,.nc,.h5,.hdf5,.jp2,.png,.jpg,.jpeg"


def configure_logging() -> None:
    """Configure default logging for the smoke-test script."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def write_raster(path: Path, *, driver: str, dtype: str = "uint16") -> None:
    """Write a tiny georeferenced raster fixture."""
    profile = {
        "driver": driver,
        "height": 8,
        "width": 8,
        "count": 1,
        "dtype": dtype,
        "crs": "EPSG:4326",
        "transform": from_origin(-180, 90, 1, 1),
    }
    data = np.arange(64, dtype=dtype).reshape(1, 8, 8)

    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(data)


def run_command(command: list[str], *, cwd: Path | None = None) -> None:
    """Run a command and raise if it fails."""
    LOGGER.info("running: %s", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def maybe_run_command(command: list[str]) -> bool:
    """Run a fixture-generation command when its executable is available."""
    if shutil.which(command[0]) is None:
        LOGGER.warning(
            "skipping %s fixture because %s is not installed", command[-1], command[0]
        )
        return False

    run_command(command)
    return True


def write_hdf5_fixture(path: Path) -> bool:
    """Write a small HDF5 fixture with h5import when that tool is available."""
    if shutil.which("h5import") is None:
        LOGGER.warning("skipping %s fixture because h5import is not installed", path)
        return False

    data_path = path.with_suffix(".h5-data.txt")
    config_path = path.with_suffix(".h5import.conf")
    data_path.write_text("1 2 3 4\n5 6 7 8\n", encoding="utf-8")
    config_path.write_text(
        "\n".join(
            [
                "PATH /data",
                "INPUT-CLASS TEXTUIN",
                "INPUT-SIZE 8",
                "INPUT-BYTE-ORDER LE",
                "RANK 2",
                "DIMENSION-SIZES 2 4",
                "OUTPUT-CLASS UIN",
                "OUTPUT-SIZE 8",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_command(["h5import", str(data_path), "-c", str(config_path), "-o", str(path)])
    return True


def generate_fixtures(input_dir: Path) -> list[Path]:
    """Generate local files in formats commonly readable by GDAL/rasterio."""
    input_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    geotiff = input_dir / "sample-geotiff.tif"
    write_raster(geotiff, driver="GTiff")
    created.append(geotiff)

    cog = input_dir / "sample-cog.tif"
    write_raster(cog, driver="COG")
    created.append(cog)

    conversions = [
        ("netCDF", input_dir / "sample-netcdf.nc"),
        ("JP2OpenJPEG", input_dir / "sample-jpeg2000.jp2"),
        ("PNG", input_dir / "sample.png"),
        ("JPEG", input_dir / "sample.jpg"),
    ]
    for driver, output_path in conversions:
        if maybe_run_command(
            ["gdal_translate", "-q", "-of", driver, str(geotiff), str(output_path)]
        ):
            created.append(output_path)

    hdf5 = input_dir / "sample-hdf5.h5"
    if write_hdf5_fixture(hdf5):
        created.append(hdf5)

    (input_dir / "skip-me.txt").write_text("not a raster\n", encoding="utf-8")
    return created


def log_rasterio_open_results(paths: list[Path]) -> None:
    """Log whether rasterio can open each generated fixture."""
    for path in paths:
        with rasterio.open(path) as dataset:
            LOGGER.info(
                "rasterio opened %-24s driver=%s size=%sx%s bands=%s crs=%s",
                path.name,
                dataset.driver,
                dataset.width,
                dataset.height,
                dataset.count,
                dataset.crs,
            )


def run_generator(
    args: argparse.Namespace, repo_root: Path, source: str, output_dir: Path
) -> None:
    """Run the project entry point selected by the caller."""
    if args.runner == "run-sh":
        run_command(
            [
                str(repo_root / "run.sh"),
                source,
                args.region,
                args.include_extensions,
                args.exclude_extensions,
            ],
            cwd=output_dir.parent,
        )
        return

    run_command(
        [
            "uv",
            "run",
            str(repo_root / "main.py"),
            f"--source={source}",
            f"--output_dir={output_dir}",
            f"--region={args.region}",
            f"--include-extensions={args.include_extensions}",
            f"--exclude-extensions={args.exclude_extensions}",
        ],
        cwd=repo_root,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate local GDAL/rasterio fixtures in /tmp and run this project against them."
    )
    parser.add_argument(
        "--runner",
        choices=("main-py", "run-sh"),
        default="main-py",
        help="Project entry point to exercise.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Directory to create/use. Defaults to a new /tmp/dps-stac-local-* directory.",
    )
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--include-extensions", default=DEFAULT_EXTENSIONS)
    parser.add_argument("--exclude-extensions", default=".txt,.xml")
    return parser.parse_args()


def main() -> None:
    """Generate fixtures, run the STAC item generator, and print output paths."""
    configure_logging()
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    work_dir = args.work_dir or Path(
        tempfile.mkdtemp(prefix="dps-stac-local-", dir="/tmp")
    )
    input_dir = work_dir / "input"
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    fixtures = generate_fixtures(input_dir)
    log_rasterio_open_results(fixtures)

    source = input_dir.resolve().as_uri()
    run_generator(args, repo_root, source, output_dir)

    LOGGER.info("input fixtures: %s", input_dir)
    LOGGER.info("STAC output: %s", output_dir)
    LOGGER.info("catalog: %s", output_dir / "catalog.json")


if __name__ == "__main__":
    main()
