"""Command-line interface for the DPS STAC item generator."""

import argparse
import logging
from pathlib import Path

from dps_stac_item_generator.generator import run


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
        default=None,
        help="Comma-separated list of file extensions to include. Use an empty string to include all files.",
    )
    parser.add_argument(
        "--exclude-extensions",
        default="",
        help="Comma-separated list of file extensions to exclude. Exclusions override inclusions.",
    )
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config", type=Path, help="Path to a JSON cataloging configuration."
    )
    config_group.add_argument(
        "--config-json", help="Inline JSON cataloging configuration."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned Items and assets without reading rasters or publishing.",
    )
    parser.add_argument(
        "--legacy-naming",
        action="store_true",
        help="Use pre-flexible-catalog IDs; collisions still fail.",
    )
    args = parser.parse_args()

    run(
        source=args.source,
        output_dir=Path(args.output_dir),
        region=args.region,
        include_extensions=args.include_extensions,
        exclude_extensions=args.exclude_extensions,
        config_path=args.config,
        config_json=args.config_json,
        dry_run=args.dry_run,
        legacy_naming=args.legacy_naming,
    )


if __name__ == "__main__":
    main()
