"""Tests for DPS STAC item generation."""

from datetime import UTC, datetime
from pathlib import Path

from pystac import Item, MediaType

from dps_stac_item_generator import generator


def test_normalize_extensions_accepts_strings_and_iterables() -> None:
    """Extension filters are normalized for consistent matching."""
    assert generator.normalize_extensions("tif, .NC, ,Tiff") == (".tif", ".nc", ".tiff")
    assert generator.normalize_extensions(["nc", ".tif", "NC"]) == (".nc", ".tif")


def test_should_include_file_applies_exclusions_after_inclusions() -> None:
    """Exclude filters win over include filters."""
    assert generator.should_include_file("s3://bucket/a.nc", (".tif", ".nc"), ())
    assert not generator.should_include_file(
        "s3://bucket/a.nc", (".tif", ".nc"), (".nc",)
    )
    assert generator.should_include_file("s3://bucket/a.h5", (), ())


def test_media_type_for_extension_handles_known_types_and_cogs() -> None:
    """Known extensions use specific media types."""
    assert generator.media_type_for_extension(".nc") == MediaType.NETCDF
    assert generator.media_type_for_extension(".tif") == MediaType.GEOTIFF
    assert generator.media_type_for_extension(".tif", is_cog=True) == MediaType.COG
    assert generator.media_type_for_extension(".unknown") == "application/octet-stream"


def test_is_cloud_optimized_geotiff_reads_first_cog_validate_tuple_value(
    monkeypatch,
) -> None:
    """rio-cogeo returns a tuple whose first item is the validation result."""

    def validate(_source: str) -> tuple[bool, list[str], list[str]]:
        return False, ["not a COG"], []

    monkeypatch.setattr(generator, "cog_validate", validate)

    assert not generator.is_cloud_optimized_geotiff("s3://bucket/not-cog.tif")


def test_run_filters_extensions_and_assigns_media_types(
    monkeypatch, tmp_path: Path
) -> None:
    """The catalog includes only files accepted by extension filters."""
    created_items = []

    def from_url(source: str, *, region: str) -> str:
        assert source == "s3://bucket/prefix"
        assert region == "us-west-2"
        return "store"

    def list_objects(_store: str) -> list[list[dict[str, str]]]:
        return [
            [
                {"path": "image.tif"},
                {"path": "cube.nc"},
                {"path": "notes.txt"},
            ]
        ]

    def create_item(**kwargs) -> Item:
        created_items.append(kwargs)
        return Item(
            id=kwargs["id"],
            geometry=None,
            bbox=None,
            datetime=datetime(2026, 1, 1, tzinfo=UTC),
            properties={},
        )

    def validate(_source: str) -> tuple[bool, list[str], list[str]]:
        return True, [], []

    monkeypatch.setattr(generator, "from_url", from_url)
    monkeypatch.setattr(generator.obstore, "list", list_objects)
    monkeypatch.setattr(generator, "create_stac_item", create_item)
    monkeypatch.setattr(generator, "cog_validate", validate)

    generator.run(
        source="s3://bucket/prefix",
        output_dir=tmp_path,
        include_extensions=".tif,.nc,.txt",
        exclude_extensions=".txt",
    )

    assert [item["id"] for item in created_items] == ["image", "cube"]
    assert created_items[0]["asset_media_type"] == MediaType.COG
    assert created_items[1]["asset_media_type"] == MediaType.NETCDF
    assert (tmp_path / "catalog.json").exists()
