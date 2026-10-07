"""Generate STAC catalogs for selected raster and attachment assets."""

import hashlib
import json
import logging
import re
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import quote, urlsplit, urlunsplit

import obstore
from obstore.store import from_url
from pystac import Asset, Catalog, CatalogType, MediaType
from rio_cogeo.cogeo import cog_validate
from rio_stac import create_stac_item

logger = logging.getLogger(__name__)

DEFAULT_REGION = "us-west-2"
DEFAULT_INCLUDE_EXTENSIONS = (".tif", ".tiff", ".nc")
_EXTENSION_MEDIA_TYPES = {
    ".tif": MediaType.GEOTIFF,
    ".tiff": MediaType.GEOTIFF,
    ".nc": MediaType.NETCDF,
}
_ALLOWED_CONFIG_FIELDS = {
    "path_pattern",
    "item_id_template",
    "asset_key_template",
    "datetime_template",
    "reference_asset",
    "required_assets",
    "non_raster_assets",
}
_TEMPLATE_FIELD = re.compile(r"\{([A-Za-z_]\w*)\}")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def normalize_extensions(extensions: str | Iterable[str] | None) -> tuple[str, ...]:
    """Normalize file extensions to lowercase dotted suffixes."""
    if extensions is None:
        return ()
    raw_extensions = (
        extensions.split(",") if isinstance(extensions, str) else extensions
    )
    normalized = []
    for extension in raw_extensions:
        extension = extension.strip().lower()
        if extension:
            normalized.append(
                extension if extension.startswith(".") else f".{extension}"
            )
    return tuple(dict.fromkeys(normalized))


def should_include_file(
    path: str, include_extensions: Iterable[str], exclude_extensions: Iterable[str] = ()
) -> bool:
    """Return whether a path passes extension filters; exclusions always win."""
    suffix = PurePosixPath(path).suffix.lower()
    excluded = tuple(exclude_extensions)
    included = tuple(include_extensions)
    return suffix not in excluded and (not included or suffix in included)


def media_type_for_extension(
    extension: str, *, is_cog: bool = False
) -> MediaType | str:
    """Return the STAC media type for a normalized suffix."""
    if extension in {".tif", ".tiff"} and is_cog:
        return MediaType.COG
    return _EXTENSION_MEDIA_TYPES.get(extension, "application/octet-stream")


def is_cloud_optimized_geotiff(source: str) -> bool:
    """Return whether a GeoTIFF source is a valid Cloud Optimized GeoTIFF."""
    result = cog_validate(source)
    return bool(result[0] if isinstance(result, tuple) else result)


def create_item_id(path: str) -> str:
    """Create a readable, collision-resistant ID from a canonical source URL."""
    stem = PurePosixPath(urlsplit(path).path).stem
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_") or "item"
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
    return f"{readable}-{digest}"


def _load_config(config_path: Path | None) -> dict:
    if config_path is None:
        return {}
    try:
        value = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read JSON config {config_path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("Config must be a JSON object")
    unknown = set(value) - _ALLOWED_CONFIG_FIELDS
    if unknown:
        raise ValueError(f"Unknown config field(s): {', '.join(sorted(unknown))}")
    pattern = value.get("path_pattern")
    if not isinstance(pattern, str):
        raise ValueError("Config path_pattern must be a regex string")
    try:
        compiled = re.compile(pattern)
    except re.error as error:
        raise ValueError(f"Invalid path_pattern: {error}") from error
    if compiled.groups == 0:
        raise ValueError("path_pattern must define at least one named capture")
    if not compiled.groupindex:
        raise ValueError("path_pattern must define named captures")
    for key in ("item_id_template", "asset_key_template", "datetime_template"):
        template = value.get(key)
        if template is not None:
            if not isinstance(template, str) or not template:
                raise ValueError(f"{key} must be a non-empty string")
            stripped = _TEMPLATE_FIELD.sub("", template)
            if "{" in stripped or "}" in stripped:
                raise ValueError(f"Invalid substitution template {key}")
            names = set(_TEMPLATE_FIELD.findall(template))
            missing = names - set(compiled.groupindex)
            if missing:
                raise ValueError(
                    f"{key} references missing capture(s): {', '.join(sorted(missing))}"
                )
    if "item_id_template" in value and "asset_key_template" not in value:
        raise ValueError("asset_key_template is required when item_id_template is set")
    if "item_id_template" in value and "datetime_template" not in value:
        raise ValueError("Grouped mode requires datetime_template")
    if "item_id_template" in value and "reference_asset" not in value:
        raise ValueError("Grouped mode requires reference_asset")
    for field in ("reference_asset",):
        if field in value and not isinstance(value[field], str):
            raise ValueError(f"{field} must be a string")
    required = value.get("required_assets", [])
    if not isinstance(required, list) or not all(
        isinstance(entry, str) for entry in required
    ):
        raise ValueError("required_assets must be an array of strings")
    attachments = value.get("non_raster_assets", {})
    if not isinstance(attachments, dict):
        raise ValueError("non_raster_assets must be an object keyed by extension")
    for extension, definition in attachments.items():
        if (
            not isinstance(extension, str)
            or not extension.startswith(".")
            or not isinstance(definition, dict)
        ):
            raise ValueError(
                "non_raster_assets entries require dotted extensions and objects"
            )
        if set(definition) - {"media_type", "roles"} or not isinstance(
            definition.get("media_type"), str
        ):
            raise ValueError(f"Invalid non_raster_assets definition for {extension}")
        roles = definition.get("roles", [])
        if not isinstance(roles, list) or not all(
            isinstance(role, str) for role in roles
        ):
            raise ValueError(f"Invalid roles for {extension}")
    value["_compiled_pattern"] = compiled
    return value


def _source_url(source: str, relative_path: str) -> str:
    """Join a POSIX relative object path to a source URL without OS path rules."""
    parts = urlsplit(source)
    path = f"{parts.path.rstrip('/')}/{quote(relative_path, safe='/@:+')}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _template(template: str, captures: dict[str, str]) -> str:
    return _TEMPLATE_FIELD.sub(lambda match: captures[match.group(1)], template)


def _atomic_catalog(items: list, output_dir: Path) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.stage-", dir=output_dir.parent)
    )
    backup = output_dir.with_name(f".{output_dir.name}.backup")
    try:
        catalog = Catalog(
            id="DPS", description="DPS", catalog_type=CatalogType.SELF_CONTAINED
        )
        for item in items:
            catalog.add_item(item)
        catalog.normalize_and_save(
            root_href=str(stage / "catalog.json"),
            catalog_type=CatalogType.SELF_CONTAINED,
        )
        if backup.exists():
            shutil.rmtree(backup)
        if output_dir.exists():
            output_dir.rename(backup)
        try:
            stage.rename(output_dir)
        except Exception:
            if backup.exists():
                backup.rename(output_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def run(
    source: str,
    output_dir: Path,
    region: str | None = None,
    include_extensions: str | Iterable[str] | None = None,
    exclude_extensions: str | Iterable[str] | None = None,
    config_path: Path | None = None,
    dry_run: bool = False,
    legacy_naming: bool = False,
) -> None:
    """Plan selected assets, extract raster metadata, and publish a STAC catalog."""
    config = _load_config(config_path)
    include = (
        DEFAULT_INCLUDE_EXTENSIONS
        if include_extensions is None
        else normalize_extensions(include_extensions)
    )
    exclude = normalize_extensions(exclude_extensions)
    attachments = {
        key.lower(): value for key, value in config.get("non_raster_assets", {}).items()
    }
    # Configured attachment formats join the defaults, but explicit CLI include filters replace them.
    if config and include_extensions is None:
        include = tuple(dict.fromkeys((*include, *attachments)))
    store = from_url(source, region=region or DEFAULT_REGION)
    listed = [obj["path"] for batch in obstore.list(store) for obj in batch]
    matched: list[tuple[str, str, dict[str, str], bool]] = []
    filtered = unmatched = 0
    pattern = config.get("_compiled_pattern")
    for path in sorted(set(listed)):
        suffix = PurePosixPath(path).suffix.lower()
        if not should_include_file(path, include, exclude):
            filtered += 1
            continue
        is_attachment = suffix in attachments
        if is_attachment and not pattern:
            filtered += 1
            continue
        captures: dict[str, str] = {}
        if pattern:
            match = pattern.fullmatch(path)
            if match is None:
                unmatched += 1
                continue
            captures = match.groupdict()
        matched.append((path, _source_url(source, path), captures, is_attachment))

    planned: dict[str, list[tuple[str, str, dict[str, str], bool, str]]] = defaultdict(
        list
    )
    for path, href, captures, attachment in matched:
        if config.get("item_id_template"):
            if any(value is None for value in captures.values()):
                raise ValueError(f"Missing regex capture for {path!r}")
            item_id = _template(config["item_id_template"], captures)
            asset_key = _template(config["asset_key_template"], captures)
        elif config:
            item_id = (
                str(PurePosixPath(path).with_suffix(""))
                if legacy_naming
                else create_item_id(href)
            )
            asset_key = (
                _template(config.get("asset_key_template", "asset"), captures)
                if pattern
                else "asset"
            )
        else:
            item_id = (
                str(PurePosixPath(path).with_suffix(""))
                if legacy_naming
                else create_item_id(href)
            )
            asset_key = "asset"
        if not _SAFE_ID.fullmatch(item_id):
            raise ValueError(f"Unsafe item ID {item_id!r} from {path!r}")
        if not _SAFE_ID.fullmatch(asset_key):
            raise ValueError(f"Unsafe asset key {asset_key!r} from {path!r}")
        planned[item_id].append((path, href, captures, attachment, asset_key))

    for item_id, entries in planned.items():
        keys = [entry[4] for entry in entries]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate asset key in Item {item_id!r}")
        if config.get("item_id_template"):
            required = set(config.get("required_assets", []))
            absent = required - set(keys)
            if absent:
                raise ValueError(
                    f"Item {item_id!r} missing required asset(s): {', '.join(sorted(absent))}"
                )
            reference = config["reference_asset"]
            if reference not in keys:
                raise ValueError(
                    f"Item {item_id!r} missing reference asset {reference!r}"
                )

    if config.get("item_id_template"):
        for item_id, entries in planned.items():
            for path, _href, captures, attachment, _key in entries:
                if not attachment:
                    dt_text = _template(config["datetime_template"], captures)
                    try:
                        parsed_datetime = datetime.fromisoformat(
                            dt_text.replace("Z", "+00:00")
                        )
                    except ValueError as error:
                        raise ValueError(
                            f"Invalid datetime {dt_text!r} for {path!r}; use ISO-8601"
                        ) from error
                    if parsed_datetime.tzinfo is None:
                        raise ValueError(
                            f"Datetime for {path!r} must include a timezone"
                        )

    if dry_run:
        for item_id, entries in sorted(planned.items()):
            logger.info(
                "Item %s: %s",
                item_id,
                ", ".join(f"{entry[4]}={entry[0]}" for entry in entries),
            )
        logger.info(
            "Plan: %d item(s), %d unmatched, %d filtered",
            len(planned),
            unmatched,
            filtered,
        )
        return

    items = []
    for item_id, entries in sorted(planned.items()):
        entries.sort(key=lambda entry: (entry[4], entry[0]))
        if not config.get("item_id_template"):
            path, href, _captures, attachment, asset_key = entries[0]
            if attachment:
                continue
            suffix = PurePosixPath(path).suffix.lower()
            is_cog = suffix in {".tif", ".tiff"} and is_cloud_optimized_geotiff(href)
            item = create_stac_item(
                source=href,
                id=item_id,
                asset_name=asset_key,
                with_proj=True,
                with_raster=True,
                asset_media_type=media_type_for_extension(suffix, is_cog=is_cog),
            )
            items.append(item)
            continue

        assets = {}
        reference_item = None
        ext_set = set()
        for path, href, captures, attachment, asset_key in entries:
            suffix = PurePosixPath(path).suffix.lower()
            if attachment:
                definition = attachments[suffix]
                assets[asset_key] = Asset(
                    href=href,
                    media_type=definition["media_type"],
                    roles=definition.get("roles", []),
                )
                continue
            dt_text = _template(config["datetime_template"], captures)
            try:
                parsed_datetime = datetime.fromisoformat(dt_text.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError(
                    f"Invalid datetime {dt_text!r} for {path!r}; use ISO-8601"
                ) from error
            if parsed_datetime.tzinfo is None:
                raise ValueError(f"Datetime for {path!r} must include a timezone")
            is_cog = suffix in {".tif", ".tiff"} and is_cloud_optimized_geotiff(href)
            source_item = create_stac_item(
                source=href,
                id=item_id,
                with_proj=True,
                with_raster=True,
                asset_name=asset_key,
                asset_media_type=media_type_for_extension(suffix, is_cog=is_cog),
                input_datetime=parsed_datetime,
            )
            source_asset = source_item.assets[asset_key]
            proj_fields = {
                key: value
                for key, value in source_item.properties.items()
                if key.startswith("proj:")
            }
            source_asset.extra_fields.update(proj_fields)
            for key in proj_fields:
                del source_item.properties[key]
            assets[asset_key] = source_asset
            ext_set.update(source_item.stac_extensions)
            if asset_key == config["reference_asset"]:
                reference_item = source_item
        if reference_item is None:
            raise ValueError(f"Item {item_id!r} has no raster reference")
        reference_item.assets.clear()
        for key, asset in assets.items():
            reference_item.add_asset(key, asset)
        reference_item.stac_extensions = sorted(ext_set)
        items.append(reference_item)

    _atomic_catalog(items, output_dir)
    logger.info("Published catalog with %d item(s) to %s", len(items), output_dir)
