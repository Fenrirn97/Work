"""Reference-vs-count and old-vs-new inventory comparison logic."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .rules import group_entries, normalize_color_key, normalize_make_key


def _add_match_keys(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the normalized identity used by movement and review workflows."""

    for result in results:
        result["match_key"] = (
            f"{normalize_make_key(result.get('item'))}|{normalize_color_key(result.get('color'))}"
        )
    return results


def _reference_amount(value: Any) -> dict[str, Any]:
    text = "" if value is None else str(value).strip()
    try:
        normalized = text.replace(",", "")
        number = Decimal(normalized)
        if not number.is_finite() or number < 0 or number != number.to_integral_value():
            raise InvalidOperation
        integer = int(number)
        return {"valid": True, "value": integer, "display": f"{integer:,}"}
    except (InvalidOperation, ValueError):
        return {"valid": False, "value": -1, "display": text or "(blank)"}


def _baseline(reference: dict[str, Any]) -> dict[str, Any]:
    start = _reference_amount(reference.get("start_text"))
    end = _reference_amount(reference.get("end_text"))
    if start["valid"]:
        used = "START (START != END)" if end["valid"] and end["value"] != start["value"] else "START"
        return {"valid": True, "value": start["value"], "start": start, "end": end, "used": used}
    if end["valid"]:
        return {
            "valid": True,
            "value": end["value"],
            "start": start,
            "end": end,
            "used": "END (START unavailable)",
        }
    return {"valid": False, "value": -1, "start": start, "end": end, "used": "NO VALID START OR END"}


def _contains_component(make_key: str, component: Any) -> bool:
    normalized = normalize_make_key(component)
    return not normalized or f" {normalized} " in f" {make_key} "


def _find_reference_match(group: dict[str, Any], references: list[dict[str, Any]]) -> dict[str, Any]:
    same_color = [row for row in references if row["color_key"] == group["color_key"]]
    if not same_color:
        return {"status": "NOT FOUND", "rows": []}
    exact = [row for row in same_color if row["make_key"] == group["make_key"]]
    if exact:
        return {"status": "EXACT", "rows": exact}
    component_matches = []
    for candidate in same_color:
        if (
            _contains_component(candidate["make_key"], group["model_key"])
            and _contains_component(candidate["make_key"], group["ram_key"])
            and _contains_component(candidate["make_key"], group["storage_key"])
        ):
            component_matches.append(candidate)
    if component_matches:
        return {"status": "ALIAS", "rows": component_matches}
    same_model = [
        row for row in same_color if _contains_component(row["make_key"], group["model_key"])
    ]
    if same_model:
        return {"status": "ATTRIBUTE CONFLICT", "rows": same_model}
    return {"status": "NOT FOUND", "rows": []}


def compare_reference(
    entries: list[dict[str, Any]],
    references: list[dict[str, Any]],
    include_missing_reference: bool = True,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    matched_ids: set[str] = set()
    for group in group_entries(entries):
        match = _find_reference_match(group, references)
        if match["status"] == "NOT FOUND":
            results.append(
                {
                    "result": "NOT IN REFERENCE",
                    "item": group["item"],
                    "color": group["color"],
                    "counted": group["amount"],
                    "baseline": None,
                    "end_value": None,
                    "difference": None,
                    "broken_amount": group["broken_amount"],
                    "source_rows": group["source_rows"],
                    "last_updated": "",
                    "explanation": "No reference item matched Model, RAM, Storage, and Color.",
                }
            )
            continue
        if match["status"] == "ATTRIBUTE CONFLICT":
            results.append(
                {
                    "result": "ATTRIBUTE CONFLICT",
                    "item": group["item"],
                    "color": group["color"],
                    "counted": group["amount"],
                    "baseline": None,
                    "end_value": None,
                    "difference": None,
                    "broken_amount": group["broken_amount"],
                    "source_rows": group["source_rows"],
                    "last_updated": "",
                    "explanation": "The model and color are similar, but RAM or Storage does not match.",
                }
            )
            continue

        candidates = match["rows"]
        reference = max(
            candidates,
            key=lambda row: (row.get("last_updated_sort", float("-inf")), row.get("row_number", 0)),
        )
        matched_ids.update(row["reference_id"] for row in candidates)
        baseline = _baseline(reference)
        end_amount = _reference_amount(reference.get("end_text"))
        if not baseline["valid"]:
            results.append(
                {
                    "result": "INVALID REFERENCE",
                    "item": group["item"],
                    "color": group["color"],
                    "counted": group["amount"],
                    "baseline": None,
                    "end_value": None,
                    "difference": None,
                    "broken_amount": group["broken_amount"],
                    "source_rows": group["source_rows"],
                    "last_updated": reference.get("last_updated", ""),
                    "explanation": "START and END are missing or invalid.",
                }
            )
            continue
        difference = baseline["value"] - group["amount"]
        result_type = "MATCH" if difference == 0 else ("MISSING ITEMS" if difference > 0 else "EXTRA ITEMS")
        results.append(
            {
                "result": result_type,
                "item": group["item"],
                "color": group["color"],
                "counted": group["amount"],
                "baseline": baseline["value"],
                "end_value": end_amount["value"] if end_amount["valid"] else None,
                "difference": difference,
                "broken_amount": group["broken_amount"],
                "source_rows": group["source_rows"],
                "last_updated": reference.get("last_updated", ""),
                "explanation": f"{baseline['used']}; Difference = baseline minus counted.",
            }
        )

    if include_missing_reference:
        for reference in references:
            if reference["reference_id"] in matched_ids:
                continue
            baseline = _baseline(reference)
            end_amount = _reference_amount(reference.get("end_text"))
            results.append(
                {
                    "result": "MISSING FROM COUNT" if baseline["valid"] else "INVALID REFERENCE",
                    "item": reference["make"],
                    "color": reference["color"] or "(blank)",
                    "counted": 0,
                    "baseline": baseline["value"] if baseline["valid"] else None,
                    "end_value": end_amount["value"] if end_amount["valid"] else None,
                    "difference": baseline["value"] if baseline["valid"] else None,
                    "broken_amount": 0,
                    "source_rows": 0,
                    "last_updated": reference.get("last_updated", ""),
                    "explanation": (
                        "Reference item was not present in the count."
                        if baseline["valid"]
                        else "Reference item is missing a valid START and END."
                    ),
                }
            )
    return _add_match_keys(results)


def compare_old_new(
    old_entries: list[dict[str, Any]], new_entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    old_groups = group_entries(old_entries)
    new_groups = group_entries(new_entries)
    old_index = {group["match_key"]: group for group in old_groups}
    new_index = {group["match_key"]: group for group in new_groups}

    for old in old_groups:
        new = new_index.get(old["match_key"])
        if new:
            difference = new["amount"] - old["amount"]
            results.append(
                {
                    "result": "MATCH" if difference == 0 else "AMOUNT CHANGED",
                    "item": new["item"],
                    "color": new["color"],
                    "counted": new["amount"],
                    "baseline": old["amount"],
                    "end_value": new["amount"],
                    "difference": difference,
                    "broken_amount": new["broken_amount"],
                    "source_rows": new["source_rows"],
                    "last_updated": "",
                    "explanation": "Difference = new count minus old count.",
                }
            )
        else:
            results.append(
                {
                    "result": "MISSING IN NEW",
                    "item": old["item"],
                    "color": old["color"],
                    "counted": 0,
                    "baseline": old["amount"],
                    "end_value": 0,
                    "difference": -old["amount"],
                    "broken_amount": 0,
                    "source_rows": 0,
                    "last_updated": "",
                    "explanation": "Item existed in the old count but is absent from the new count.",
                }
            )
    for new in new_groups:
        if new["match_key"] in old_index:
            continue
        results.append(
            {
                "result": "NEW ITEM",
                "item": new["item"],
                "color": new["color"],
                "counted": new["amount"],
                "baseline": 0,
                "end_value": new["amount"],
                "difference": new["amount"],
                "broken_amount": new["broken_amount"],
                "source_rows": new["source_rows"],
                "last_updated": "",
                "explanation": "Item exists in the new count but not in the old count.",
            }
        )
    return _add_match_keys(results)
