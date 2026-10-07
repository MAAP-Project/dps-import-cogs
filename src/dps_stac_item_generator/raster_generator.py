"""Generate a two-tile, three-channel synthetic happy-face raster demo."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

LOGGER = logging.getLogger(__name__)
DEFAULT_SIZE = 256
PIXEL_SIZE = 100.0
CRS = "EPSG:3857"


def make_rgb_image(size: int) -> np.ndarray:
    """Create a colorful RGB face on a contrasting background."""
    x = (np.arange(size * 2, dtype=np.float32) + 0.5) / (size * 2)
    y = (np.arange(size, dtype=np.float32) + 0.5) / size
    xx, yy = np.meshgrid(x, y)
    image = np.empty((3, size, size * 2), dtype=np.uint8)

    image[0] = np.clip(35 + 50 * xx, 0, 255).astype(np.uint8)
    image[1] = np.clip(150 - 70 * xx, 0, 255).astype(np.uint8)
    image[2] = np.clip(205 - 35 * yy, 0, 255).astype(np.uint8)

    face = ((xx - 0.5) / 0.39) ** 2 + ((yy - 0.5) / 0.43) ** 2 <= 1
    image[0][face] = 255
    image[1][face] = 190
    image[2][face] = 45

    eyes = (((xx - 0.405) / 0.035) ** 2 + ((yy - 0.405) / 0.055) ** 2 <= 1) | (
        ((xx - 0.595) / 0.035) ** 2 + ((yy - 0.405) / 0.055) ** 2 <= 1
    )
    image[0][eyes] = 30
    image[1][eyes] = 35
    image[2][eyes] = 95

    mouth_x = (xx >= 0.335) & (xx <= 0.665)
    mouth_curve = 0.70 - 1.8 * (xx - 0.5) ** 2
    smile = mouth_x & (np.abs(yy - mouth_curve) <= 0.012)
    image[0][smile] = 185
    image[1][smile] = 25
    image[2][smile] = 65

    cheeks = (((xx - 0.355) / 0.045) ** 2 + ((yy - 0.535) / 0.025) ** 2 <= 1) | (
        ((xx - 0.645) / 0.045) ** 2 + ((yy - 0.535) / 0.025) ** 2 <= 1
    )
    image[0][cheeks] = 245
    image[1][cheeks] = 75
    image[2][cheeks] = 105
    return image


def generate(output_dir: Path, size: int = DEFAULT_SIZE) -> list[Path]:
    """Write six adjacent, single-band RGB-channel Cloud Optimized GeoTIFFs."""
    if size < 32:
        raise ValueError("size must be at least 32 pixels")
    output_dir.mkdir(parents=True, exist_ok=True)
    rgb = make_rgb_image(size)
    created: list[Path] = []
    channel_names = ("red", "green", "blue")

    for tile_index, tile in enumerate(("left", "right")):
        tile_data = rgb[:, :, tile_index * size : (tile_index + 1) * size]
        transform = from_origin(
            (tile_index - 1) * size * PIXEL_SIZE,
            size * PIXEL_SIZE,
            PIXEL_SIZE,
            PIXEL_SIZE,
        )
        for channel_index, channel in enumerate(channel_names):
            path = output_dir / tile / f"{channel}.tif"
            path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(
                path,
                "w",
                driver="COG",
                height=size,
                width=size,
                count=1,
                dtype="uint8",
                crs=CRS,
                transform=transform,
            ) as dataset:
                dataset.write(tile_data[channel_index], 1)
                dataset.set_band_description(1, channel)
            created.append(path)

    LOGGER.info("Wrote %d single-band COGs under %s", len(created), output_dir)
    return created


def main() -> None:
    """Generate the demo files from command-line arguments."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir", type=Path, help="Directory for left/ and right/ tiles"
    )
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_SIZE,
        help=f"Pixels per tile side (default: {DEFAULT_SIZE}; minimum: 32)",
    )
    args = parser.parse_args()
    generate(args.output_dir, args.size)


if __name__ == "__main__":
    main()
