"""Validation and product-identity rules shared by the API and comparator."""

from __future__ import annotations

import re
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


class InventoryError(ValueError):
    """A user-correctable inventory validation error."""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_match_text(value: Any) -> str:
    return clean_text(value).upper()


def normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", clean_text(value).lower())


def normalize_make_key(value: Any) -> str:
    text = normalize_match_text(value)
    text = re.sub(r"\b([0-9]+)\s*(GB|TB)\b", r"\1", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text.strip())


def normalize_color_key(value: Any) -> str:
    return normalize_match_text(value)


def is_zero_memory(value: Any) -> bool:
    text = normalize_match_text(value)
    text = re.sub(r"\s*(GB|TB)\s*$", "", text)
    if not text:
        return False
    try:
        return Decimal(text) == 0
    except InvalidOperation:
        return False


def is_non_memory_item(ram: Any, storage: Any) -> bool:
    return is_zero_memory(ram) and is_zero_memory(storage)


def has_partial_zero_memory(ram: Any, storage: Any) -> bool:
    return is_zero_memory(ram) != is_zero_memory(storage)


def remove_memory_unit(value: Any) -> str:
    return re.sub(r"(?i)\s*(GB|TB)\s*$", "", clean_text(value))


def count_make(model: Any, ram: Any, storage: Any) -> str:
    model_text = clean_text(model)
    if is_non_memory_item(ram, storage):
        return model_text
    return f"{model_text} {remove_memory_unit(ram)}+{remove_memory_unit(storage)}".strip()


def item_details(entry: dict[str, Any], include_broken_box: bool = True) -> str:
    parts = [clean_text(entry.get("model"))]
    if not is_non_memory_item(entry.get("ram"), entry.get("storage")):
        parts.extend([clean_text(entry.get("ram")), clean_text(entry.get("storage"))])
    if include_broken_box and bool(entry.get("broken_box")):
        parts.append("Broken Box")
    return " · ".join(part for part in parts if part)


def comparison_key(model: Any, ram: Any, storage: Any, color: Any) -> str:
    make = count_make(model, ram, storage)
    return f"{normalize_make_key(make)}|{normalize_color_key(color)}"


def parse_whole_number(value: Any, label: str, *, allow_zero: bool = True) -> int:
    text = clean_text(value).replace(",", "")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        raise InventoryError(f"{label} must be a whole number.") from None
    if not number.is_finite() or number != number.to_integral_value():
        raise InventoryError(f"{label} must be a whole number.")
    integer = int(number)
    if integer < 0 or (not allow_zero and integer == 0):
        qualifier = "greater than zero" if not allow_zero else "zero or greater"
        raise InventoryError(f"{label} must be {qualifier}.")
    if integer > 9_223_372_036_854_775_807:
        raise InventoryError(f"{label} is too large.")
    return integer


def validate_entry(payload: dict[str, Any]) -> dict[str, Any]:
    model = clean_text(payload.get("model"))
    ram = clean_text(payload.get("ram"))
    storage = clean_text(payload.get("storage"))
    color = clean_text(payload.get("color"))
    area = clean_text(payload.get("area"))

    if not model:
        raise InventoryError("Enter the Model.")
    if not ram:
        raise InventoryError("Enter RAM. Use 0 when the item has no RAM.")
    if not storage:
        raise InventoryError("Enter Storage. Use 0 when the item has no Storage.")
    if has_partial_zero_memory(ram, storage):
        raise InventoryError(
            "RAM and Storage must both be 0 for a non-memory item. A partial zero is not allowed."
        )
    if not color:
        raise InventoryError("Enter the Color.")
    if not area:
        raise InventoryError("Enter the Area or warehouse location.")

    items_per_box = parse_whole_number(payload.get("items_per_box", 0), "Items per Box")
    boxes = parse_whole_number(payload.get("boxes", 0), "Boxes")
    loose_items = parse_whole_number(payload.get("loose_items", 0), "Loose Items")
    amount = (items_per_box * boxes) + loose_items
    if amount <= 0:
        raise InventoryError("The calculated Amount must be greater than zero.")

    return {
        "model": model,
        "ram": ram,
        "storage": storage,
        "color": color.title(),
        "items_per_box": items_per_box,
        "boxes": boxes,
        "loose_items": loose_items,
        "amount": amount,
        "area": area,
        "broken_box": bool(payload.get("broken_box", False)),
    }


def group_entries(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in rows:
        key = comparison_key(row.get("model"), row.get("ram"), row.get("storage"), row.get("color"))
        if key not in grouped:
            non_memory = is_non_memory_item(row.get("ram"), row.get("storage"))
            grouped[key] = {
                "match_key": key,
                "make_key": normalize_make_key(
                    count_make(row.get("model"), row.get("ram"), row.get("storage"))
                ),
                "model_key": normalize_make_key(row.get("model")),
                "ram_key": "" if non_memory else normalize_make_key(row.get("ram")),
                "storage_key": "" if non_memory else normalize_make_key(row.get("storage")),
                "color_key": normalize_color_key(row.get("color")),
                "model": clean_text(row.get("model")),
                "ram": clean_text(row.get("ram")),
                "storage": clean_text(row.get("storage")),
                "color": clean_text(row.get("color")),
                "make": count_make(row.get("model"), row.get("ram"), row.get("storage")),
                "item": item_details(row, include_broken_box=False),
                "amount": 0,
                "broken_amount": 0,
                "source_rows": 0,
            }
        group = grouped[key]
        amount = int(row.get("amount") or 0)
        group["amount"] += amount
        if bool(row.get("broken_box")):
            group["broken_amount"] += amount
        group["source_rows"] += 1
    return list(grouped.values())
