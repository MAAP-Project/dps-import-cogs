"""Generate a two-tile, three-channel synthetic happy-face raster demo."""

from dps_stac_item_generator.raster_generator import (
    DEFAULT_SIZE,
    generate,
    main,
    make_rgb_image,
)

__all__ = ["DEFAULT_SIZE", "generate", "make_rgb_image", "main"]


if __name__ == "__main__":
    main()
