"""Resolve products and classify live-versus-catalog bullet points."""

from __future__ import annotations

from dataclasses import dataclass, field
import html
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

from .all_listings import AllListingsIndex, load_all_listings
from .catalog_reader import (
    CatalogData,
    CatalogProduct,
    clean_asin,
    load_catalog,
    sku_key,
    with_product_asins,
)
from .comparison_report import write_comparison_report
from .live_records import LiveProduct, build_live_results


EXACT_MATCH = "Exact Match"
FORMATTING_ONLY = "Formatting Only"
TEXT_CHANGED = "Text Changed"
MISSING_LIVE = "Missing Live"
MISSING_CATALOG = "Missing Catalog"
BULLET_MOVED = "Bullet Moved"

STATUS_ORDER = (
    TEXT_CHANGED,
    MISSING_LIVE,
    MISSING_CATALOG,
    BULLET_MOVED,
    FORMATTING_ONLY,
    EXACT_MATCH,
)
REVIEW_STATUSES = frozenset(
    {TEXT_CHANGED, MISSING_LIVE, MISSING_CATALOG, BULLET_MOVED}
)


@dataclass(frozen=True)
class BulletComparison:
    asin: str
    product_name: str
    sku: str
    matched_via: str
    catalog_position: int | None
    live_position: int | None
    status: str
    catalog_value: str
    live_value: str

    @property
    def catalog_field(self) -> str:
        if self.catalog_position is None:
            return "(none)"
        return f"Bullet Point {self.catalog_position}"

    @property
    def live_field(self) -> str:
        if self.live_position is None:
            return "(none)"
        return f"Bullet Point {self.live_position}"

    @property
    def needs_review(self) -> bool:
        return self.status in REVIEW_STATUSES


@dataclass
class ComparisonResult:
    comparisons: list[BulletComparison]
    live_problems: list[LiveProduct]
    not_in_catalog: list[LiveProduct]
    stats: dict[str, int]
    unresolved_catalog: list[CatalogProduct] = field(default_factory=list)

    @property
    def issues(self) -> list[BulletComparison]:
        return [item for item in self.comparisons if item.needs_review]

    @property
    def comparisons_by_asin(self) -> dict[str, list[BulletComparison]]:
        return _group_by_asin(self.comparisons)

    @property
    def issues_by_asin(self) -> dict[str, list[BulletComparison]]:
        return _group_by_asin(self.issues)


@dataclass(frozen=True)
class PreparedComparison:
    records: list[dict[str, Any]]
    requested_asins: list[str]
    catalog: CatalogData
    all_listings: AllListingsIndex | None
    resolution_stats: dict[str, int]
    unresolved_catalog: list[CatalogProduct]


def _group_by_asin(
    comparisons: Iterable[BulletComparison],
) -> dict[str, list[BulletComparison]]:
    grouped: dict[str, list[BulletComparison]] = {}
    for comparison in comparisons:
        grouped.setdefault(comparison.asin, []).append(comparison)
    return grouped


def normalize_text(value: Any) -> str:
    """Remove presentation-only differences before comparing bullet text."""
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKC", text)
    text = (
        text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2022", " ")
    )
    text = re.sub(r"[\s\.,;:!?()\[\]{}\-_/\\]+", " ", text)
    return text.strip().casefold()


def unique_catalog_rows(products: Iterable[CatalogProduct]) -> list[CatalogProduct]:
    """Avoid reporting duplicate catalog rows while preserving real variants."""
    unique = []
    seen = set()
    for product in products:
        key = (
            product.asin,
            sku_key(product.sku),
            tuple(normalize_text(value) for value in product.bullets),
        )
        if key not in seen:
            seen.add(key)
            unique.append(product)
    return unique


def resolve_catalog_asins(
    catalog: CatalogData,
    live_results: Mapping[str, LiveProduct],
    all_listings: AllListingsIndex | None = None,
    manual_resolutions: Mapping[int, str] | None = None,
) -> tuple[CatalogData, dict[str, int], list[CatalogProduct]]:
    """Resolve blank catalog ASINs by SKU, unique name, then user input."""
    title_to_asins: dict[str, set[str]] = {}
    for live in live_results.values():
        if not live.can_compare:
            continue
        title_key = normalize_text(live.title)
        if title_key:
            title_to_asins.setdefault(title_key, set()).add(live.requested_asin)

    stats = {
        "catalog_asins_present": 0,
        "catalog_asins_resolved_by_sku": 0,
        "catalog_asins_resolved_by_name": 0,
        "catalog_asins_resolved_by_user": 0,
        "catalog_asins_unresolved": 0,
    }
    replacements: dict[int, tuple[str, str]] = {}
    manual_resolutions = manual_resolutions or {}

    for product in catalog.products:
        if product.asin:
            stats["catalog_asins_present"] += 1
            continue

        asin = ""
        source = ""
        if all_listings and product.sku:
            asin = clean_asin(all_listings.sku_to_asin.get(sku_key(product.sku)))
            if asin:
                source = "SKU via All Listings TXT"

        if not asin:
            title_key = normalize_text(product.product_name)
            possible_asins = title_to_asins.get(title_key, set()) if title_key else set()
            if len(possible_asins) == 1:
                asin = next(iter(possible_asins))
                source = "Product Name"

        if not asin:
            asin = clean_asin(manual_resolutions.get(product.source_row))
            if asin:
                source = "User-entered ASIN"

        if not asin:
            continue

        replacements[product.source_row] = (asin, source)
        stats_key = {
            "SKU via All Listings TXT": "catalog_asins_resolved_by_sku",
            "Product Name": "catalog_asins_resolved_by_name",
            "User-entered ASIN": "catalog_asins_resolved_by_user",
        }[source]
        stats[stats_key] += 1

    resolved_catalog = with_product_asins(catalog, replacements)
    unresolved = [product for product in resolved_catalog.products if not product.asin]
    stats["catalog_asins_unresolved"] = len(unresolved)
    return resolved_catalog, stats, unresolved


def _match_method(products: list[CatalogProduct], default: str) -> str:
    sources = {product.asin_source for product in products if product.asin_source}
    non_catalog_sources = sources - {"Catalog ASIN"}
    if len(non_catalog_sources) == 1 and "Catalog ASIN" not in sources:
        return next(iter(non_catalog_sources))
    return default


def find_catalog_matches(
    live: LiveProduct,
    catalog: CatalogData,
    all_listings: AllListingsIndex | None,
) -> tuple[list[CatalogProduct], str]:
    """Match by ASIN first, then SKU, then a unique product name."""
    for asin, method in (
        (live.requested_asin, "ASIN"),
        (live.returned_asin, "Returned ASIN"),
    ):
        if asin and asin in catalog.products_by_asin:
            products = unique_catalog_rows(catalog.products_by_asin[asin])
            return products, _match_method(products, method)

    if all_listings:
        matches: list[CatalogProduct] = []
        candidate_asins = dict.fromkeys(
            asin for asin in (live.requested_asin, live.returned_asin) if asin
        )
        for asin in candidate_asins:
            for sku in all_listings.asin_to_skus.get(asin, []):
                matches.extend(catalog.products_by_sku.get(sku_key(sku), []))
        matches = unique_catalog_rows(matches)
        if matches:
            return matches, "SKU via All Listings TXT"

    title_key = normalize_text(live.title)
    if title_key:
        matches = unique_catalog_rows(
            product
            for product in catalog.products
            if normalize_text(product.product_name) == title_key
        )
        if len(matches) == 1:
            return matches, "Product Name"

    return [], ""


def _comparison(
    live: LiveProduct,
    catalog_product: CatalogProduct,
    *,
    matched_via: str,
    catalog_position: int | None,
    live_position: int | None,
    status: str,
    catalog_value: str,
    live_value: str,
) -> BulletComparison:
    return BulletComparison(
        asin=live.requested_asin,
        product_name=catalog_product.product_name or live.title,
        sku=catalog_product.sku,
        matched_via=matched_via,
        catalog_position=catalog_position,
        live_position=live_position,
        status=status,
        catalog_value=catalog_value or "(blank)",
        live_value=live_value or "(blank)",
    )


def _same_position_status(catalog_value: str, live_value: str) -> str:
    if catalog_value == live_value:
        return EXACT_MATCH
    if normalize_text(catalog_value) == normalize_text(live_value):
        return FORMATTING_ONLY
    if catalog_value and not live_value:
        return MISSING_LIVE
    if live_value and not catalog_value:
        return MISSING_CATALOG
    return TEXT_CHANGED


def compare_bullets(
    live: LiveProduct,
    catalog_product: CatalogProduct,
    matched_via: str = "ASIN",
) -> list[BulletComparison]:
    """Classify five catalog bullets against five live bullets."""
    catalog_values = (list(catalog_product.bullets[:5]) + [""] * 5)[:5]
    live_values = (list(live.bullets[:5]) + [""] * 5)[:5]
    catalog_norms = [normalize_text(value) for value in catalog_values]
    live_norms = [normalize_text(value) for value in live_values]

    matched_catalog: set[int] = set()
    matched_live: set[int] = set()
    results: list[BulletComparison] = []

    for index in range(5):
        if not catalog_values[index] and not live_values[index]:
            continue
        if catalog_norms[index] and catalog_norms[index] == live_norms[index]:
            results.append(
                _comparison(
                    live,
                    catalog_product,
                    matched_via=matched_via,
                    catalog_position=index + 1,
                    live_position=index + 1,
                    status=_same_position_status(
                        catalog_values[index], live_values[index]
                    ),
                    catalog_value=catalog_values[index],
                    live_value=live_values[index],
                )
            )
            matched_catalog.add(index)
            matched_live.add(index)

    move_candidates = []
    for catalog_index in range(5):
        if catalog_index in matched_catalog or not catalog_norms[catalog_index]:
            continue
        for live_index in range(5):
            if live_index in matched_live or not live_norms[live_index]:
                continue
            if (
                catalog_index != live_index
                and catalog_norms[catalog_index] == live_norms[live_index]
            ):
                move_candidates.append(
                    (abs(catalog_index - live_index), catalog_index, live_index)
                )

    for _distance, catalog_index, live_index in sorted(move_candidates):
        if catalog_index in matched_catalog or live_index in matched_live:
            continue
        results.append(
            _comparison(
                live,
                catalog_product,
                matched_via=matched_via,
                catalog_position=catalog_index + 1,
                live_position=live_index + 1,
                status=BULLET_MOVED,
                catalog_value=catalog_values[catalog_index],
                live_value=live_values[live_index],
            )
        )
        matched_catalog.add(catalog_index)
        matched_live.add(live_index)

    for index in range(5):
        if index in matched_catalog or index in matched_live:
            continue
        if not catalog_values[index] and not live_values[index]:
            continue
        results.append(
            _comparison(
                live,
                catalog_product,
                matched_via=matched_via,
                catalog_position=index + 1 if catalog_values[index] else None,
                live_position=index + 1 if live_values[index] else None,
                status=_same_position_status(
                    catalog_values[index], live_values[index]
                ),
                catalog_value=catalog_values[index],
                live_value=live_values[index],
            )
        )
        if catalog_values[index]:
            matched_catalog.add(index)
        if live_values[index]:
            matched_live.add(index)

    for index in range(5):
        if index not in matched_catalog and catalog_values[index]:
            results.append(
                _comparison(
                    live,
                    catalog_product,
                    matched_via=matched_via,
                    catalog_position=index + 1,
                    live_position=None,
                    status=MISSING_LIVE,
                    catalog_value=catalog_values[index],
                    live_value="",
                )
            )
        if index not in matched_live and live_values[index]:
            results.append(
                _comparison(
                    live,
                    catalog_product,
                    matched_via=matched_via,
                    catalog_position=None,
                    live_position=index + 1,
                    status=MISSING_CATALOG,
                    catalog_value="",
                    live_value=live_values[index],
                )
            )

    status_rank = {status: index for index, status in enumerate(STATUS_ORDER)}
    return sorted(
        results,
        key=lambda item: (
            item.catalog_position or item.live_position or 99,
            item.live_position or 99,
            status_rank[item.status],
        ),
    )


def compare_records(
    records: list[dict[str, Any]],
    requested_asins: Sequence[str],
    catalog: CatalogData,
    all_listings: AllListingsIndex | None = None,
    *,
    unresolved_catalog: list[CatalogProduct] | None = None,
    resolution_stats: Mapping[str, int] | None = None,
) -> ComparisonResult:
    live_results = build_live_results(records, requested_asins)
    comparisons: list[BulletComparison] = []
    live_problems: list[LiveProduct] = []
    not_in_catalog: list[LiveProduct] = []
    match_counts: dict[str, int] = {}
    stats = {
        "requested": 0,
        "found": 0,
        "redirected": 0,
        "not_found": 0,
        "extraction_failed": 0,
        "not_in_catalog": 0,
        **dict(resolution_stats or {}),
    }

    for raw_asin in requested_asins:
        asin = clean_asin(raw_asin)
        if not asin:
            continue
        stats["requested"] += 1
        live = live_results[asin]

        if not live.can_compare:
            live_problems.append(live)
            if live.status == "Redirected":
                stats["redirected"] += 1
            elif live.status == "Extraction Failed":
                stats["extraction_failed"] += 1
            else:
                stats["not_found"] += 1
            continue

        stats["found"] += 1
        catalog_products, matched_via = find_catalog_matches(
            live, catalog, all_listings
        )
        if not catalog_products:
            not_in_catalog.append(live)
            stats["not_in_catalog"] += 1
            continue

        match_counts[matched_via] = match_counts.get(matched_via, 0) + 1
        for catalog_product in catalog_products:
            comparisons.extend(
                compare_bullets(live, catalog_product, matched_via=matched_via)
            )

    result = ComparisonResult(
        comparisons,
        live_problems,
        not_in_catalog,
        stats,
        unresolved_catalog or [],
    )
    status_keys = {
        EXACT_MATCH: "exact_match_rows",
        FORMATTING_ONLY: "formatting_only_rows",
        TEXT_CHANGED: "text_changed_rows",
        MISSING_LIVE: "missing_live_rows",
        MISSING_CATALOG: "missing_catalog_rows",
        BULLET_MOVED: "bullet_moved_rows",
    }
    for status, key in status_keys.items():
        stats[key] = sum(item.status == status for item in comparisons)
    for method in (
        "ASIN",
        "Returned ASIN",
        "SKU via All Listings TXT",
        "Product Name",
        "User-entered ASIN",
    ):
        key = "matched_by_" + re.sub(r"[^a-z0-9]+", "_", method.casefold()).strip("_")
        stats[key] = match_counts.get(method, 0)

    stats["comparison_rows"] = len(comparisons)
    stats["issue_rows"] = len(result.issues)
    stats["issue_asins"] = len(result.issues_by_asin)
    stats["catalog_not_live_asins"] = len(live_problems)
    stats["not_in_catalog_asins"] = len(not_in_catalog)
    return result


def prepare_comparison(
    records: list[dict[str, Any]],
    requested_asins: Sequence[str],
    catalog_path: str | Path,
    all_listings_path: str | Path | None = None,
    manual_resolutions: Mapping[int, str] | None = None,
) -> PreparedComparison:
    clean_requested = [asin for value in requested_asins if (asin := clean_asin(value))]
    live_results = build_live_results(records, clean_requested)
    catalog = load_catalog(catalog_path)
    all_listings = load_all_listings(all_listings_path) if all_listings_path else None
    catalog, resolution_stats, unresolved = resolve_catalog_asins(
        catalog,
        live_results,
        all_listings,
        manual_resolutions,
    )
    return PreparedComparison(
        records,
        clean_requested,
        catalog,
        all_listings,
        resolution_stats,
        unresolved,
    )


def write_prepared_comparison(
    prepared: PreparedComparison,
    output_path: str | Path,
) -> dict[str, int | str]:
    comparison = compare_records(
        prepared.records,
        prepared.requested_asins,
        prepared.catalog,
        prepared.all_listings,
        unresolved_catalog=prepared.unresolved_catalog,
        resolution_stats=prepared.resolution_stats,
    )
    write_comparison_report(output_path, comparison)
    return {
        **comparison.stats,
        "catalog_records": prepared.catalog.record_count,
        "catalog_sheet": prepared.catalog.sheet_name,
        "all_listings_rows": (
            prepared.all_listings.row_count if prepared.all_listings else 0
        ),
    }


def run_comparison_from_records(
    records: list[dict[str, Any]],
    requested_asins: Sequence[str],
    catalog_path: str | Path,
    output_path: str | Path,
    all_listings_path: str | Path | None = None,
    manual_resolutions: Mapping[int, str] | None = None,
) -> dict[str, int | str]:
    prepared = prepare_comparison(
        records,
        requested_asins,
        catalog_path,
        all_listings_path,
        manual_resolutions,
    )
    return write_prepared_comparison(prepared, output_path)
