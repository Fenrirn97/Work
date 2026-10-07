"""Use Amazon's All Listings TXT as an optional ASIN-to-SKU bridge."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .catalog_reader import clean_asin, clean_text, normalize_header, sku_key


@dataclass(frozen=True)
class AllListingsIndex:
    asin_to_skus: dict[str, list[str]]
    sku_to_asin: dict[str, str]
    row_count: int


def load_all_listings(path: str | Path) -> AllListingsIndex:
    path = Path(path)
    if not path.is_file():
        raise ValueError("All Listings TXT file was not found.")

    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            with path.open("r", encoding=encoding, newline="") as file_handle:
                reader = csv.DictReader(file_handle, delimiter="\t")
                if not reader.fieldnames:
                    raise ValueError("All Listings TXT has no header row.")

                headers = {
                    normalize_header(header): header
                    for header in reader.fieldnames
                    if header
                }
                sku_column = headers.get("seller sku") or headers.get("sku")
                asin_column = headers.get("asin1") or headers.get("asin")
                if not sku_column or not asin_column:
                    raise ValueError(
                        "All Listings TXT must contain seller-sku and asin1 columns."
                    )

                asin_to_skus: dict[str, list[str]] = {}
                sku_to_asin: dict[str, str] = {}
                row_count = 0
                for row in reader:
                    sku = clean_text(row.get(sku_column))
                    if not sku:
                        continue
                    row_count += 1
                    asin = clean_asin(row.get(asin_column))
                    if not asin:
                        continue
                    key = sku_key(sku)
                    sku_to_asin[key] = asin
                    bucket = asin_to_skus.setdefault(asin, [])
                    if key not in {sku_key(existing) for existing in bucket}:
                        bucket.append(sku)

                return AllListingsIndex(asin_to_skus, sku_to_asin, row_count)
        except UnicodeDecodeError as exc:
            last_error = exc

    raise ValueError(f"Could not read All Listings TXT: {last_error}")