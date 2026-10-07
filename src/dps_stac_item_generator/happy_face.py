"""Build a self-contained happy-face demo output for DPS."""

from __future__ import annotations

import argparse
import logging
import shutil
import tempfile
from pathlib import Path

from pystac import Catalog

from dps_stac_item_generator import generator
from dps_stac_item_generator.raster_generator import generate

LOGGER = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).resolve().parents[2] / "examples" / "happy-face.json"


def run(output_dir: Path, size: int = 256) -> None:
    """Generate local RGB COGs and publish them with their STAC catalog."""
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}.happy-face-", dir=output_dir.parent
    ) as temporary_dir:
        temporary = Path(temporary_dir)
        rasters_dir = temporary / "rasters"
        generate(rasters_dir, size)

        # generator.run atomically replaces output_dir, so keep source rasters
        # outside it until catalog publication has completed.
        generator.run(
            source=rasters_dir.as_uri(),
            output_dir=output_dir,
            config_path=CONFIG_PATH,
        )
        assets_dir = output_dir / "rasters"
        assets_dir.mkdir()
        catalog = Catalog.from_file(str(output_dir / "catalog.json"))
        for item in catalog.get_items(recursive=True):
            for channel, asset in item.assets.items():
                tile = item.id.removeprefix("happy-face-")
                bundled_raster = assets_dir / f"{item.id}-{channel}.tif"
                shutil.copyfile(rasters_dir / tile / f"{channel}.tif", bundled_raster)
                # Set an absolute on-disk href, then let PySTAC calculate the
                # relative href from each item's self href. It remains valid
                # when the returned Directory is relocated as a unit.
                asset.href = str(bundled_raster)

        catalog.make_all_asset_hrefs_relative()
        catalog.save()
    LOGGER.info("Published self-contained happy-face demo to %s", output_dir)


def main() -> None:
    """Run the happy-face DPS demo from command-line arguments."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output_dir", type=Path, required=True)
    parser.add_argument("--size", type=int, default=256)
    args = parser.parse_args()
    run(args.output_dir, args.size)


if __name__ == "__main__":
    main()
