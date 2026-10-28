"""Turn raw Bright Data product records into simple live-page statuses."""


from __future__ import annotations


import ast
from dataclasses import dataclass
import json
import re
from typing import Any, Iterable


from .catalog_reader import clean_asin, clean_text




AMAZON_ASIN_IN_URL = re.compile(
    r"/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?#]|$)",
    re.IGNORECASE,
)




@dataclass(frozen=True)
class LiveProduct:
    requested_asin: str
    returned_asin: str
    title: str
    bullets: list[str]
    page_url: str
    status: str
    message: str


    @property
    def can_compare(self) -> bool:
        return self.status == "Found"




def list_values(value: Any) -> list[str]:
    """Read Bright Data list fields without caring how the provider encoded them."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [clean_text(item) for item in value if clean_text(item)]
    if isinstance(value, dict):
        return [clean_text(item) for item in value.values() if clean_text(item)]


    text = clean_text(value)
    if not text:
        return []


    if text[0] in "[{" and text[-1] in "]}":
        for parser in (json.loads, ast.literal_eval):
            try:
                return list_values(parser(text))
            except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
                pass


    if "\n" in text or "\r" in text:
        return [line.strip(" \t-*•") for line in re.split(r"[\r\n]+", text) if line.strip(" \t-*•")]
    if "•" in text:
        return [part.strip() for part in text.split("•") if part.strip()]
    return [text]




def asin_from_url(url: str) -> str:
    match = AMAZON_ASIN_IN_URL.search(url or "")
    return clean_asin(match.group(1)) if match else ""




def page_url(record: dict[str, Any]) -> str:
    for field in ("url", "origin_url", "input_url"):
        value = clean_text(record.get(field))
        if value:
            return value
    return ""




def record_score(record: dict[str, Any]) -> int:
    """Prefer the most complete record when Bright Data returns duplicates."""
    score = 0
    if not clean_text(record.get("error")):
        score += 10
    if clean_text(record.get("title")):
        score += 5
    score += min(5, len(list_values(record.get("features"))))
    if page_url(record):
        score += 1
    return score




def index_raw_records(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index provider rows by the ASIN that was submitted to Bright Data."""
    indexed: dict[str, dict[str, Any]] = {}


    for record in records:
        if not isinstance(record, dict):
            continue


        requested_asin = clean_asin(record.get("input_asin"))
        if not requested_asin:
            requested_asin = asin_from_url(clean_text(record.get("input_url")))
        if not requested_asin:
            requested_asin = clean_asin(record.get("asin"))
        if not requested_asin:
            continue


        previous = indexed.get(requested_asin)
        if previous is None or record_score(record) > record_score(previous):
            indexed[requested_asin] = record


    return indexed




def build_live_product(requested_asin: str, record: dict[str, Any] | None) -> LiveProduct:
    """Explain what Bright Data returned for one requested ASIN."""
    if record is None:
        return LiveProduct(
            requested_asin=requested_asin,
            returned_asin="",
            title="",
            bullets=[""] * 5,
            page_url="",
            status="Not Found",
            message="Bright Data returned no record for this ASIN.",
        )


    returned_asin = clean_asin(record.get("asin"))
    final_url = page_url(record)
    url_asin = asin_from_url(final_url)
    error = clean_text(record.get("error"))
    title = clean_text(record.get("title"))
    bullets = list_values(record.get("features"))[:5]
    bullets += [""] * (5 - len(bullets))


    if error:
        return LiveProduct(
            requested_asin,
            returned_asin,
            title,
            bullets,
            final_url,
            "Extraction Failed",
            error,
        )


    redirect_asin = ""
    if returned_asin and returned_asin != requested_asin:
        redirect_asin = returned_asin
    elif url_asin and url_asin != requested_asin:
        redirect_asin = url_asin


    if redirect_asin:
        return LiveProduct(
            requested_asin,
            redirect_asin,
            title,
            bullets,
            final_url,
            "Redirected",
            f"Requested {requested_asin}, but Amazon returned {redirect_asin}.",
        )


    has_product_data = bool(title or any(bullets) or final_url)
    if not has_product_data:
        return LiveProduct(
            requested_asin,
            returned_asin,
            title,
            bullets,
            final_url,
            "Not Found",
            "Bright Data returned a row, but it did not contain live product data.",
        )


    return LiveProduct(
        requested_asin,
        returned_asin or requested_asin,
        title,
        bullets,
        final_url,
        "Found",
        "Live product returned for the requested ASIN.",
    )




def build_live_results(
    records: Iterable[dict[str, Any]],
    requested_asins: Iterable[str],
) -> dict[str, LiveProduct]:
    indexed_records = index_raw_records(records)
    results = {}
    for value in requested_asins:
        asin = clean_asin(value)
        if asin:
            results[asin] = build_live_product(asin, indexed_records.get(asin))
    return results
