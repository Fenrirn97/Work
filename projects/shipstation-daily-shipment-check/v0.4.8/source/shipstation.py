

"""Read-only ShipStation extraction. Credentials and records are not persisted."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests



class ReportError(Exception):
    def __init__(self, message, code="REPORT_ERROR"):
        super().__init__(message)
        self.code = code


""" ----------- 1 - CHECK USER INPUT ----------- """


def parse_credentials(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 16384:
        raise ReportError("Choose a TXT file smaller than 16 KB.")
    lines = [
        s.strip()
        for s in text.lstrip("\ufeff").splitlines()
        if s.strip() and not s.strip().startswith("#")
    ]
    aliases = {
        "key": ("API_KEY", "V1_API_KEY", "SHIPSTATION_API_KEY"),
        "secret": ("API_SECRET", "V1_API_SECRET", "SHIPSTATION_API_SECRET"),
        "v2": ("V2_API_KEY", "SHIPSTATION_V2_API_KEY"),
    }
    allowed = {name for names in aliases.values() for name in names}
    fields = {}
    for line in lines:
        match = re.fullmatch(r"([a-zA-Z][a-zA-Z0-9_ -]*)\s*[:=]\s*(.+)", line)
        if not match:
            continue
        name = re.sub(r"[ -]", "_", match[1].strip().upper())
        if name not in allowed:
            continue
        if name in fields:
            raise ReportError("The TXT file repeats a credential field.")
        fields[name] = match[2].strip().strip("\"'")
    values = {}
    for group, names in aliases.items():
        found = [fields[name] for name in names if name in fields]
        if len(found) > 1:
            raise ReportError("Keep only one key and its matching secret in the file.")
        values[group] = found[0] if found else ""
    key, secret, v2 = (values[k] for k in ("key", "secret", "v2"))
    if v2 and (key or secret):
        raise ReportError("Use V1 key + secret OR one V2 key, not both.")
    if secret and not key or "V1_API_KEY" in fields and not secret:
        raise ReportError("V1 requires both API_KEY and API_SECRET.")
    value = v2 or key or (lines[0] if len(lines) == 1 and not fields else "")
    if not value:
        raise ReportError(
            "No API key found. Use one V2 key, or API_KEY and API_SECRET on separate lines."
        )
    for part in (value, secret):
        if part and (
            not re.fullmatch(r"[\x21-\x7e]{8,512}", part)
            or re.search(r"YOUR_|PASTE_|REPLACE_|HERE", part, re.I)
        ):
            raise ReportError(
                "Replace the example text with real credentials. Keys cannot contain spaces."
            )
    return {"version": "v1" if secret else "v2", "key": value, "secret": secret}


def parse_ship_date(value):
    value = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            value = date.fromisoformat(value).strftime("%m/%d/%Y")
        except ValueError:
            raise ReportError("Enter a real calendar date between 2000 and 2099.") from None
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        raise ReportError("Enter Ship Date as MM/DD/YYYY, for example 08/27/2026.")
    try:
        result = datetime.strptime(value, "%m/%d/%Y").date()
        if not 2000 <= result.year <= 2099:
            raise ValueError()
    except ValueError:
        raise ReportError("Enter a real calendar date between 2000 and 2099.") from None
    return {
        "display": value,
        "iso": result.isoformat(),
        "next": (result + timedelta(days=1)).isoformat(),
    }


def parse_ship_date_range(start_value, end_value=None):
    """Inclusive calendar dates. The query's upper bound is the next midnight."""
    start = parse_ship_date(start_value)
    end = parse_ship_date(end_value if end_value not in (None, "") else start_value)
    if end["iso"] < start["iso"]:
        raise ReportError("Through date must be the same as or later than From date.")
    days = (date.fromisoformat(end["iso"]) - date.fromisoformat(start["iso"])).days + 1
    single = start["iso"] == end["iso"]
    return {
        "iso": start["iso"], "end": end["iso"], "next": end["next"],
        "startDisplay": start["display"], "endDisplay": end["display"], "days": days,
        "display": start["display"] if single else start["display"] + " through " + end["display"],
        "fileRange": start["iso"] if single else start["iso"] + "_to_" + end["iso"],
    }


def ship_date_in_range(value, selected):
    calendar = calendar_date(value)
    return bool(calendar and selected["iso"] <= calendar <= selected.get("end", selected["iso"]))


def calendar_date(value):
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            pass
    return ""


def as_id(value):
    return "" if value is None else str(value)


def number_or_none(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def joined(values):
    return "; ".join(dict.fromkeys(str(v) for v in values if v is not None and v != ""))


""" ----------- 2 - CONNECT TO SHIPSTATION ----------- """


class ShipStationAPI:
    def __init__(
        self,
        credentials,
        progress=lambda message: None,
        session=None,
        interval=None,
        sleep=time.sleep,
    ):
        self.version = credentials["version"]
        self.base = (
            "https://ssapi.shipstation.com"
            if self.version == "v1"
            else "https://api.shipstation.com/v2"
        )
        self.headers = {"Accept": "application/json"}
        if self.version == "v1":
            pair = (credentials["key"] + ":" + credentials["secret"]).encode("ascii")
            self.headers["Authorization"] = "Basic " + base64.b64encode(pair).decode("ascii")
        else:
            self.headers["api-key"] = credentials["key"]
        self.session = session if session is not None else requests.Session()
        self.interval = (
            interval if interval is not None else (1.6 if self.version == "v1" else 0.35)
        )
        self.progress, self.sleep, self.next_allowed = progress, sleep, 0

    def get(self, path, **params):
        if not re.fullmatch(r"/(orders|shipments|fulfillments|labels|stores)(/[^/?#]+)?", path):
            raise ReportError("Unsupported API resource.")
        for attempt in range(4):
            if self.next_allowed > time.monotonic():
                self.sleep(self.next_allowed - time.monotonic())
            try:
                # Explicit auth prevents an unrelated .netrc login overriding the uploaded key.
                response = self.session.get(
                    self.base + path,
                    params=params,
                    headers=self.headers,
                    timeout=(10, 45),
                    allow_redirects=False,
                    auth=lambda request: request,
                )
            except requests.RequestException:
                if attempt == 3:
                    raise ReportError(
                        "Cannot reach ShipStation. Check your internet connection and try again.",
                        "NETWORK",
                    ) from None
                self.sleep(2**attempt)
                continue
            finally:
                self.next_allowed = time.monotonic() + self.interval
            status = response.status_code
            if status == 401:
                raise ReportError(
                    "ShipStation rejected the credentials. Check API version, key and V1 secret.",
                    "AUTH",
                )
            if status in (402, 403):
                raise ReportError(
                    "Your ShipStation account or key cannot access this API. Check plan and permissions.",
                    "ACCESS",
                )
            if status == 429 or status >= 500:
                if attempt == 3:
                    raise ReportError(
                        "ShipStation is busy or rate-limiting requests. Retry later; no partial file was created.",
                        "RETRY_LIMIT",
                    )
                retry = response.headers.get("Retry-After") or response.headers.get(
                    "X-Rate-Limit-Reset"
                )
                try:
                    seconds = float(retry) if retry is not None else 2**attempt
                except ValueError:
                    try:
                        seconds = max(0, parsedate_to_datetime(retry).timestamp() - time.time())
                    except (ValueError, TypeError, OverflowError):
                        seconds = 2**attempt
                if not math.isfinite(seconds):
                    seconds = 2**attempt
                if seconds > 300:
                    raise ReportError(
                        "ShipStation requested a long pause. Please retry in a few minutes.",
                        "RATE_LIMIT",
                    )
                self.progress("ShipStation requested a pause; retrying safely...")
                self.sleep(max(1, seconds + 0.2))
                continue
            if not 200 <= status < 300:
                raise ReportError(
                    f"ShipStation returned HTTP {status} for {path.split('/')[1]}. No partial file was created.",
                    f"HTTP_{status}",
                )
            try:
                data = response.json()
            except ValueError:
                raise ReportError(
                    "ShipStation returned an unexpected response instead of JSON.", "BAD_RESPONSE"
                ) from None
            if response.headers.get("X-Rate-Limit-Remaining") == "0":
                reset = number_or_none(response.headers.get("X-Rate-Limit-Reset")) or 60
                if reset > 300:
                    raise ReportError(
                        "ShipStation requested a long pause. Please retry later.", "RATE_LIMIT"
                    )
                self.next_allowed = time.monotonic() + max(0, reset)
            return data
        raise ReportError("ShipStation requests could not be completed.")

    def get_pages(self, path, key, **params):
        size = 500 if self.version == "v1" else 100
        size_key = "pageSize" if self.version == "v1" else "page_size"
        seen, received = set(), 0
        section_started = time.monotonic()
        for page in range(1, 1001):
            self.progress(f"Reading {key}: page {page}...")
            result = self.get(path, **params, page=page, **{size_key: size})
            rows = result.get(key) if isinstance(result, dict) else None
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ReportError(
                    f"ShipStation did not return the expected {key} list.", "BAD_RESPONSE"
                )
            pages, total = number_or_none(result.get("pages")), number_or_none(result.get("total"))
            if not rows:
                if total is not None and total > received or pages is not None and pages > page:
                    raise ReportError(
                        "An API page is missing. Please rerun; no partial file was created.",
                        "PAGINATION",
                    )
                return
            total_pages = (
                int(pages)
                if pages is not None and pages > 0
                else (max(1, math.ceil(total / size)) if total is not None and total > 0 else None)
            )
            if total_pages:
                average = max(self.interval + 0.25, (time.monotonic() - section_started) / page)
                self.progress(
                    {
                        "message": f"Reading {key}: page {page} of {total_pages}...",
                        "section": key.replace("_", " ").title(),
                        "currentPage": page,
                        "totalPages": total_pages,
                        "estimatedSeconds": math.ceil(max(0, total_pages - page) * average),
                    }
                )
            signature = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).digest()
            if signature in seen:
                raise ReportError(
                    "ShipStation repeated a page. Stopping to avoid incomplete or duplicate data.",
                    "PAGINATION",
                )
            seen.add(signature)
            received += len(rows)
            yield rows
            if pages is not None and pages > 0:
                if page >= pages:
                    return
            elif total is not None:
                if received >= total:
                    return
            elif len(rows) < size:
                return
        raise ReportError(
            "The 1,000-page safety limit was reached. No partial file was created.", "PAGINATION"
        )


""" ----------- 3 - CREATE THE EXCEL ROWS ----------- """


def make_tracking_record(record, source, version):
    v1 = version == "v1"
    return {
        "recordId": as_id(
            record.get("fulfillmentId", record.get("shipmentId"))
            if v1
            else record.get("fulfillment_id", record.get("label_id"))
        ),
        "shipmentId": as_id(record.get("shipmentId") if v1 else record.get("shipment_id")),
        "orderId": as_id(record.get("orderId") if v1 else record.get("external_order_id")),
        "orderNumber": as_id(
            record.get("orderNumber")
            if v1
            else record.get("shipment_number") or record.get("external_order_id")
        ),
        "shipDate": calendar_date(record.get("shipDate") if v1 else record.get("ship_date")),
        "tracking": joined(
            [record.get("trackingNumber") if v1 else record.get("tracking_number")]
            + [
                p.get("tracking_number") or p.get("trackingNumber")
                for p in record.get("packages") or []
            ]
        ),
        "carrier": (
            record.get("carrierCode")
            if v1
            else record.get("fulfillment_carrier_friendly_name")
            or record.get("carrier_code")
            or record.get("carrier_id")
        )
        or "",
        "service": (
            record.get("serviceCode") or record.get("fulfillmentServiceCode")
            if v1
            else record.get("fulfillment_service_code") or record.get("service_code")
        )
        or "",
        "provider": (
            record.get("sellerFillProviderName") or record.get("fulfillmentProviderCode")
            if v1
            else record.get("fulfillment_provider_friendly_name")
            or record.get("fulfillment_provider_code")
        )
        or "",
        "recipient": (record.get("shipTo" if v1 else "ship_to") or {}).get("name", ""),
        "source": source,
    }


def make_item_row(
    order_number, order_id, order_date, item, store, recipient, events, quantity_basis, warnings=()
):
    item = item or {}
    quantity, price = number_or_none(item.get("quantity")), number_or_none(
        item.get("unitPrice", item.get("unit_price"))
    )
    row = {
        "orderNumber": as_id(order_number),
        "orderId": as_id(order_id),
        "orderDate": order_date,
        "itemId": as_id(
            item.get(
                "orderItemId", item.get("sales_order_item_id", item.get("external_order_item_id"))
            )
        ),
        "itemName": item.get("name") or "",
        "sku": item.get("sku") or "",
        "quantity": quantity,
        "unitPrice": price,
        "lineTotal": quantity * price if quantity is not None and price is not None else None,
        "quantityBasis": quantity_basis,
        "store": store or "",
        "recipient": recipient or "",
        "shipDate": joined(sorted({e.get("shipDate", "") for e in events if e.get("shipDate")})),
    }
    for field, event_field in {
        "tracking": "tracking",
        "carrier": "carrier",
        "service": "service",
        "fulfillmentProvider": "provider",
        "shipmentIds": "shipmentId",
        "recordIds": "recordId",
        "source": "source",
    }.items():
        row[field] = joined(e.get(event_field) for e in events)
    notes = list(warnings)
    for key, label in (
        ("tracking", "Tracking"),
        ("sku", "SKU"),
        ("itemName", "Item name"),
        ("orderDate", "Order date"),
    ):
        if not row[key]:
            notes.append(label + " unavailable")
    if quantity is None:
        notes.append("Quantity unavailable")
    row["warnings"] = joined(notes)
    return row


""" ----------- 4 - GET A VERSION 1 REPORT ----------- """


def get_v1_report(shipstation_api, day):
    events, rows, issues, by_order, seen = [], [], [], {}, set()
    params = {"shipDateStart": day["iso"] + " 00:00:00", "shipDateEnd": day["next"] + " 00:00:00"}
    for key, source in (
        ("fulfillments", "Fulfillment / marked shipped"),
        ("shipments", "ShipStation label"),
    ):
        extra = {"includeShipmentItems": "true"} if key == "shipments" else {}
        for page in shipstation_api.get_pages("/" + key, key, **params, **extra):
            for record in page:
                if (
                    record.get("voided")
                    or record.get("voidDate")
                    or record.get("isReturnLabel")
                    or not ship_date_in_range(record.get("shipDate"), day)
                ):
                    continue
                event = make_tracking_record(record, source, "v1")
                identity = source, event["recordId"]
                if event["recordId"] and identity in seen:
                    continue
                seen.add(identity)
                events.append(event)
                if event["orderId"]:
                    by_order.setdefault(event["orderId"], []).append(event)
    stores = {}
    try:
        result = shipstation_api.get("/stores")
        if isinstance(result, list):
            stores = {as_id(s.get("storeId")): s.get("storeName") for s in result}
    except ReportError as error:
        if error.code in ("AUTH", "ACCESS"):
            raise
        issues.append("Store names unavailable; Store ID is preserved instead.")
    found = set()

    def add_order(order, matched, notes=()):
        identity = as_id(order.get("orderId"))
        if identity and identity in found:
            return
        if identity:
            found.add(identity)
        notes = list(notes)
        if not matched:
            notes.append("No matching shipment/fulfillment record in the selected range")
        if not identity:
            notes.append("Order ID unavailable; tracking cannot be matched safely")
        if len(matched) > 1:
            notes.append(
                "Multiple shipment records: tracking is order-level, not item-to-package allocation"
            )
        selected = matched or [{"shipDate": calendar_date(order.get("shipDate")), "source": "Shipped order only"}]
        items = [i for i in order.get("items") or [] if not i.get("adjustment")]
        store_id = as_id((order.get("advancedOptions") or {}).get("storeId"))
        for item in items or [None]:
            rows.append(
                make_item_row(
                    order.get("orderNumber"),
                    identity,
                    calendar_date(order.get("orderDate")),
                    item,
                    stores.get(store_id) or store_id,
                    (order.get("shipTo") or {}).get("name"),
                    selected,
                    "Order item quantity",
                    notes,
                )
            )

    is_today = day["iso"] == day.get("end", day["iso"]) == date.today().isoformat()
    if is_today:
        order_ids = sorted(by_order)
        shipstation_api.progress(
            f"Today's date selected: reading only {len(order_ids)} linked order(s)..."
        )
        details_started = time.monotonic()
        for index, identity in enumerate(order_ids, 1):
            matched = by_order[identity]
            try:
                order = shipstation_api.get("/orders/" + quote(identity, safe=""))
                if not isinstance(order, dict):
                    raise ReportError("Unexpected order detail response.", "BAD_RESPONSE")
                status = order.get("orderStatus")
                notes = (
                    []
                    if status == "shipped"
                    else [
                        f"Current order status is {status or 'unavailable'}; daily shipment retained"
                    ]
                )
                add_order(order, matched, notes)
            except ReportError as error:
                if error.code != "HTTP_404":
                    raise
                found.add(identity)
                first = matched[0]
                rows.append(
                    make_item_row(
                        first["orderNumber"],
                        identity,
                        "",
                        None,
                        "",
                        first["recipient"],
                        matched,
                        "Order item quantity",
                        ["Order detail not found; tracking record retained"],
                    )
                )
            average = max(
                shipstation_api.interval + 0.25, (time.monotonic() - details_started) / index
            )
            shipstation_api.progress(
                {
                    "message": f"Reading today's order details: order {index} of {len(order_ids)}...",
                    "section": "Today's order details",
                    "currentPage": index,
                    "totalPages": len(order_ids),
                    "estimatedSeconds": math.ceil(max(0, len(order_ids) - index) * average),
                }
            )
    else:
        shipstation_api.progress(
            "Checking Shipped order history once for the selected Ship Date range..."
        )
        for page in shipstation_api.get_pages("/orders", "orders", orderStatus="shipped"):
            for order in page:
                identity = as_id(order.get("orderId"))
                if identity in found or order.get("orderStatus") != "shipped":
                    continue
                matched = by_order.get(identity, []) if identity else []
                if not matched and not ship_date_in_range(order.get("shipDate"), day):
                    continue
                add_order(order, matched)
    for event in events:
        if event["orderId"] not in found:
            issues.append(
                f"Shipment record {event['recordId'] or '(no ID)'} is not linked to a currently Shipped order. Retained on Tracking Records."
            )
    strategy = (
        "Today's linked orders + Shipments + Fulfillments"
        if is_today
        else "Full Shipped Orders history + Shipments + Fulfillments"
    )
    return {
        "rows": rows,
        "events": events,
        "issues": issues,
        "coverage": strategy,
        "quantityNote": "Quantity is ORDER LINE quantity, not proof all units shipped in this range. Each order is listed once across the range. Split orders may span dates. Tracking is linked at order level; package allocation is not inferred.",
    }


""" ----------- 5 - GET A VERSION 2 REPORT ----------- """


def get_v2_report(shipstation_api, day):
    events, rows = [], []
    for page in shipstation_api.get_pages(
        "/fulfillments",
        "fulfillments",
        ship_date_start=day["iso"] + "T00:00:00Z",
        ship_date_end=day["next"] + "T00:00:00Z",
    ):
        for record in page:
            if (
                not record.get("voided")
                and not record.get("voided_at")
                and ship_date_in_range(record.get("ship_date"), day)
            ):
                events.append(make_tracking_record(record, "Fulfillment / marked shipped", "v2"))
    # V2 labels do not have a ship-date filter. Do not restrict label creation date.
    shipstation_api.progress("Checking completed labels by Ship Date, not label creation date...")
    for page in shipstation_api.get_pages("/labels", "labels", label_status="completed"):
        for record in page:
            if (
                not record.get("voided")
                and not record.get("voided_at")
                and not record.get("is_return_label")
                and record.get("status", "completed") == "completed"
                and ship_date_in_range(record.get("ship_date"), day)
            ):
                events.append(make_tracking_record(record, "ShipStation label", "v2"))
    events = list({(e["source"], e["recordId"] or i): e for i, e in enumerate(events)}.values())
    groups = {}
    for i, event in enumerate(events):
        groups.setdefault(event["shipmentId"] or f"unmatched:{i}", []).append(event)
    details_started = time.monotonic()
    for index, (identity, group) in enumerate(groups.items(), 1):
        shipstation_api.progress(f"Reading item details: shipment {index} of {len(groups)}...")
        shipment, notes = {}, []
        if identity.startswith("unmatched:"):
            notes.append("Shipment ID unavailable; record preserved")
        else:
            try:
                shipment = shipstation_api.get("/shipments/" + quote(identity, safe=""))
                if not isinstance(shipment, dict):
                    raise ReportError("Unexpected shipment detail response.", "BAD_RESPONSE")
            except ReportError as error:
                if error.code != "HTTP_404":
                    raise
                notes.append("Shipment detail not found; record preserved")
        average = max(shipstation_api.interval + 0.25, (time.monotonic() - details_started) / index)
        shipstation_api.progress(
            {
                "message": f"Reading item details: shipment {index} of {len(groups)}...",
                "section": "Shipment details",
                "currentPage": index,
                "totalPages": len(groups),
                "estimatedSeconds": math.ceil(max(0, len(groups) - index) * average),
            }
        )
        if len(group) > 1:
            notes.append("Multiple tracking records; item-to-package allocation is not inferred")
        for item in shipment.get("items") or [{}]:
            rows.append(
                make_item_row(
                    item.get("external_order_id")
                    or shipment.get("shipment_number")
                    or group[0]["orderNumber"],
                    item.get("sales_order_id")
                    or shipment.get("external_order_id")
                    or group[0]["orderId"],
                    "",
                    item,
                    shipment.get("order_source_code"),
                    (shipment.get("ship_to") or {}).get("name") or group[0]["recipient"],
                    group,
                    "Shipment item quantity",
                    notes,
                )
            )
    return {
        "rows": rows,
        "events": events,
        "issues": [
            "V2 does not provide the original Order Date here or exact Shipped-status order reconciliation. Use a V1 key + secret for the fuller order-based report."
        ],
        "coverage": "V2 Fulfillments + completed Labels + Shipment items (limited order metadata)",
        "quantityNote": "Quantity is SHIPMENT ITEM quantity. Labels for the same shipment are grouped so items are not multiplied by package count. Order Date is blank; shipment creation date is not substituted.",
    }


""" ----------- 6 - RUN THE COMPLETE REPORT ----------- """


def extract_report(
    credentials_text,
    ship_date,
    progress=lambda message: None,
    ship_date_end=None,
    **client_options,
):
    """Build the read-only ShipStation shipment report.

    Print-status CSV matching and carrier checks are added later by their own modules so
    the API extraction stays independent and easy to test.
    """
    credentials, day = parse_credentials(credentials_text), parse_ship_date_range(ship_date, ship_date_end)
    shipstation_api = ShipStationAPI(credentials, progress, **client_options)
    try:
        progress(
            "Credentials recognized as "
            + credentials["version"].upper()
            + ". Extracting Ship Dates " + day["display"] + " (inclusive)..."
        )
        if credentials["version"] == "v1":
            report = get_v1_report(shipstation_api, day)
        else:
            report = get_v2_report(shipstation_api, day)
    finally:
        shipstation_api.session.close()
        shipstation_api.headers.clear()
        credentials.clear()

    version = shipstation_api.version
    report["rows"].sort(key=lambda r: (r["orderNumber"], r["sku"]))

    def group_key(row):
        return (
            row["orderId"]
            if version == "v1" and row["orderId"]
            else row["shipmentIds"] or row["recordIds"] or row["orderNumber"]
        )

    report.update(
        version=version,
        shipDate=day["iso"],
        shipDateStart=day["iso"],
        shipDateEnd=day["end"],
        rangeDays=day["days"],
        fileRange=day["fileRange"],
        displayDate=day["display"],
        generatedAt=datetime.now(timezone.utc).isoformat(),
        rowCount=len(report["rows"]),
        recordCount=len({group_key(row) for row in report["rows"]}),
        missingTrackingCount=len({group_key(row) for row in report["rows"] if not row["tracking"]}),
    )
    return report
