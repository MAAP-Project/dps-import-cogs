"""Command-line interface for the DPS STAC item generator."""

import argparse
import logging
from pathlib import Path

from dps_stac_item_generator.generator import DEFAULT_INCLUDE_EXTENSIONS, run


def configure_logging() -> None:
    """Configure default process logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logging.getLogger("botocore").setLevel(logging.WARNING)


def main() -> None:
    """Parse CLI arguments and generate STAC items."""
    configure_logging()

    parser = argparse.ArgumentParser(
        description="Generate STAC item metadata for matching files in object storage."
    )
    parser.add_argument(
        "--source",
        help="Source location of the files for which you want to generate STAC items."
        " e.g. 's3://bucket/path/to/files/'",
        required=True,
    )
    parser.add_argument(
        "--output_dir",
        help="Directory in which to save output",
        required=True,
    )
    parser.add_argument(
        "--region",
        help="Region in which the storage container exists. e.g. 'us-west-2'",
        default="us-west-2",
    )
    parser.add_argument(
        "--include-extensions",
        default=",".join(DEFAULT_INCLUDE_EXTENSIONS),
        help="Comma-separated list of file extensions to include. Use an empty string to include all files.",
    )
    parser.add_argument(
        "--exclude-extensions",
        default="",
        help="Comma-separated list of file extensions to exclude. Exclusions override inclusions.",
    )
    args = parser.parse_args()

    run(
        source=args.source,
        output_dir=Path(args.output_dir),
        region=args.region,
        include_extensions=args.include_extensions,
        exclude_extensions=args.exclude_extensions,
    )


if __name__ == "__main__":
    main()
