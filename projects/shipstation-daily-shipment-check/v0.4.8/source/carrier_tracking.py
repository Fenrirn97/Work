
"""Optional public-web carrier tracking for UPS, FedEx and USPS only.

This module does not use carrier API credentials. When enabled, it opens an
installed Microsoft Edge or Google Chrome browser through Playwright, visits the
public tracking page for each unique tracking number, and reads the rendered status.
If a carrier blocks automation or asks for a CAPTCHA, the report keeps a direct
tracking link and marks the row for manual review instead of attempting to bypass it.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from shipstation import ReportError

SUPPORTED = ("UPS", "FedEx", "USPS")


def clean(value):
    return "" if value is None else str(value).strip()


def split_tracking(value):
    return [p.strip() for p in re.split(r"[;,\n\r]+", clean(value)) if p.strip()]


def valid_tracking_identifier(value):
    value = clean(value).replace(" ", "")
    if not value:
        return False
    # A value such as 9.40015020621792E+021 may already have lost digits in Excel.
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?[Ee][+-]?\d+", value):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9]{7,40}", value))


def normalize_carrier(carrier="", service="", provider="", tracking=""):
    text = " ".join([clean(carrier), clean(service), clean(provider)]).lower()
    t = clean(tracking).replace(" ", "").upper()

    if "fedex" in text or "fdxe" in text or "fdxg" in text:
        return "FedEx"
    if "usps" in text or "stamps" in text or "endicia" in text or "postal" in text:
        return "USPS"
    if re.search(r"\bups\b", text) or "ups_" in text or "ups wallet" in text:
        return "UPS"

    # Fallback only when ShipStation carrier text is unavailable/non-descriptive.
    if t.startswith("1Z") and len(t) >= 18:
        return "UPS"
    if t.isdigit() and len(t) in (20, 21, 22, 26, 34) and t.startswith(("9", "4")):
        return "USPS"
    if t.isdigit() and len(t) in (12, 15):
        return "FedEx"
    return "Unsupported"


def build_tracking_url(carrier, tracking):
    tracking = clean(tracking).replace(" ", "")
    encoded = quote(tracking, safe="")
    if carrier == "UPS":
        return f"https://www.ups.com/track?loc=en_US&tracknum={encoded}"
    if carrier == "FedEx":
        return f"https://www.fedex.com/fedextrack/?trknbr={encoded}"
    if carrier == "USPS":
        return f"https://tools.usps.com/go/TrackConfirmAction?tLabels={encoded}"
    return ""


def _base_result(tracking, carrier):
    return {
        "tracking": clean(tracking),
        "carrier": carrier,
        "trackingUrl": build_tracking_url(carrier, tracking),
        "status": "UNKNOWN",
        "statusDescription": "",
        "carrierAccepted": "Unknown",
        "firstCarrierScan": "",
        "latestScan": "",
        "latestLocation": "",
        "estimatedDelivery": "",
        "actualDelivery": "",
        "checkedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "error": "",
    }


def _finish(result, physical_seen=False):
    status = result["status"]
    if status in ("LABEL CREATED", "CANCELLED"):
        result["carrierAccepted"] = "No"
    elif status in ("CARRIER ACCEPTED", "IN TRANSIT", "OUT FOR DELIVERY", "DELIVERED"):
        result["carrierAccepted"] = "Yes"
    elif physical_seen:
        result["carrierAccepted"] = "Yes"
    else:
        result["carrierAccepted"] = "Unknown"
    return result


def _normalized_identifier(value):
    return re.sub(r"[^A-Z0-9]", "", clean(value).upper())


def _relevant_lines(text, tracking):
    lines = [re.sub(r"\s+", " ", line).strip() for line in clean(text).splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return [], False

    target = _normalized_identifier(tracking)
    found_index = None
    if target:
        for index, line in enumerate(lines):
            if target in _normalized_identifier(line):
                found_index = index
                break

    if found_index is None:
        # Do not classify help/footer text when the requested tracking identifier is
        # not visible on the rendered result page.
        return lines[:140], False

    start = max(0, found_index - 30)
    end = min(len(lines), found_index + 90)
    return lines[start:end], True


def _status_patterns(carrier):
    # Patterns are intentionally specific. The first matching line in the shipment
    # area wins so a historical "Label Created" lower on a delivered shipment does
    # not override the current Delivered status near the top.
    common = [
        ("DELIVERED", ("delivered",)),
        ("OUT FOR DELIVERY", ("out for delivery",)),
    ]
    if carrier == "UPS":
        return common + [
            ("CARRIER ACCEPTED", ("we have your package", "picked up", "origin scan")),
            ("IN TRANSIT", ("on the way", "in transit", "departed from facility", "arrived at facility")),
            ("LABEL CREATED", ("label created", "shipment ready for ups", "billing information received")),
            ("EXCEPTION", ("exception", "delay", "delivery attempted", "returning to sender")),
        ]
    if carrier == "FedEx":
        return common + [
            ("CARRIER ACCEPTED", ("we have your package", "at drop off point", "picked up")),
            ("IN TRANSIT", ("on the way", "in transit", "at fedex location", "departed fedex location")),
            ("LABEL CREATED", ("label created", "shipment information sent to fedex")),
            ("CANCELLED", ("shipment cancelled",)),
            ("EXCEPTION", ("delay", "exception", "we tried to deliver", "returning to shipper")),
        ]
    if carrier == "USPS":
        return common + [
            (
                "LABEL CREATED",
                (
                    "shipping label created, usps awaiting item",
                    "usps awaiting item",
                    "pre-shipment",
                    "pre shipment",
                    "picked up by shipping partner, usps awaiting item",
                ),
            ),
            (
                "CARRIER ACCEPTED",
                (
                    "usps in possession of item",
                    "accepted at usps",
                    "shipment received, package acceptance pending",
                ),
            ),
            (
                "IN TRANSIT",
                (
                    "moving through network",
                    "in transit to next facility",
                    "arrived at usps",
                    "departed usps",
                    "processed through usps",
                    "processing at usps",
                ),
            ),
            ("EXCEPTION", ("alert", "delivery attempted", "return to sender", "insufficient address")),
        ]
    return []


def extract_browser_status(carrier, tracking, body_text):
    """Classify the rendered public tracking page without relying on fragile CSS."""
    result = _base_result(tracking, carrier)
    lines, tracking_visible = _relevant_lines(body_text, tracking)
    if not lines:
        result.update(status="MANUAL CHECK REQUIRED", error="Carrier page returned no readable text.")
        return _finish(result)
    if not tracking_visible:
        result.update(
            status="MANUAL CHECK REQUIRED",
            error="The requested tracking number was not visible on the rendered carrier result page.",
        )
        return _finish(result)

    blocked_phrases = (
        "verify you are human",
        "captcha",
        "access denied",
        "temporarily blocked",
        "unusual traffic",
        "security check",
        "robot or a human",
    )
    joined = "\n".join(lines).lower()
    if any(phrase in joined for phrase in blocked_phrases):
        result.update(
            status="MANUAL CHECK REQUIRED",
            error="Carrier website requested human verification or blocked automated reading.",
        )
        return _finish(result)

    # Build exact match candidates with their line index. Earliest visible shipment
    # status wins; this avoids footer/help text overriding the actual status.
    candidates = []
    for status, phrases in _status_patterns(carrier):
        for line_index, line in enumerate(lines):
            lower = line.lower()
            for phrase in phrases:
                if phrase in lower:
                    candidates.append((line_index, status, line, phrase))
                    break

    if not candidates:
        # Some USPS pages use the short status "Accepted" on its own.
        if carrier == "USPS":
            for line_index, line in enumerate(lines):
                if line.strip().lower() == "accepted":
                    candidates.append((line_index, "CARRIER ACCEPTED", line, "accepted"))
                    break

    if not candidates:
        result.update(
            status="MANUAL CHECK REQUIRED",
            error="The public tracking page opened, but the program could not identify the current status.",
        )
        return _finish(result)

    candidates.sort(key=lambda item: item[0])
    _, status, line, _ = candidates[0]
    result["status"] = status
    result["statusDescription"] = line[:500]

    physical_seen = status in ("CARRIER ACCEPTED", "IN TRANSIT", "OUT FOR DELIVERY", "DELIVERED")
    return _finish(result, physical_seen=physical_seen)


def _installed_browser_paths():
    candidates = []
    env = os.environ
    roots = [env.get("PROGRAMFILES(X86)"), env.get("PROGRAMFILES"), env.get("LOCALAPPDATA")]
    for root in [p for p in roots if p]:
        candidates.extend(
            [
                Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe",
            ]
        )
    for command in ("msedge", "microsoft-edge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    unique = []
    seen = set()
    for path in candidates:
        key = str(path).lower()
        if path.is_file() and key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


class PublicTrackingBrowser:
    def __init__(self, progress=lambda message: None, visible=True):
        self.progress = progress
        self.visible = bool(visible)
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ReportError(
                "Browser tracking support is not installed. Close the program and run START.cmd again while connected to the internet."
            ) from None

        self._playwright = sync_playwright().start()
        launch_errors = []

        for channel in ("msedge", "chrome"):
            try:
                self._browser = self._playwright.chromium.launch(
                    channel=channel,
                    headless=not self.visible,
                )
                break
            except Exception as error:
                launch_errors.append(f"{channel}: {error.__class__.__name__}")

        if self._browser is None:
            for executable in _installed_browser_paths():
                try:
                    self._browser = self._playwright.chromium.launch(
                        executable_path=str(executable),
                        headless=not self.visible,
                    )
                    break
                except Exception as error:
                    launch_errors.append(f"{executable.name}: {error.__class__.__name__}")

        if self._browser is None:
            self.close()
            raise ReportError(
                "Could not start Microsoft Edge or Google Chrome for carrier tracking. "
                "Install/update Edge or Chrome, then try again."
            )

        self._context = self._browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        self._page = self._context.new_page()
        self._page.set_default_timeout(7000)
        self._page.set_default_navigation_timeout(30000)
        return self

    def close(self):
        for obj in (self._context, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        self._context = None
        self._browser = None
        self._page = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = None

    def _body_text(self):
        try:
            return self._page.locator("body").inner_text(timeout=5000)
        except Exception:
            return ""

    def _wait_for_status(self, carrier, tracking, seconds=7.5):
        deadline = time.monotonic() + seconds
        latest = ""
        while time.monotonic() < deadline:
            latest = self._body_text()
            result = extract_browser_status(carrier, tracking, latest)
            if result["status"] != "MANUAL CHECK REQUIRED":
                return result
            # When the window is visible, give the user a short chance to complete a
            # carrier-provided human-verification step. Hidden mode returns immediately.
            if "human verification" in result.get("error", "").lower() and not self.visible:
                return result
            time.sleep(0.6)
        return extract_browser_status(carrier, tracking, latest)

    def _fill_tracking_input(self, tracking):
        # Generic fallback used when a carrier changes its direct tracking URL.
        inputs = self._page.locator("input")
        try:
            count = min(inputs.count(), 40)
        except Exception:
            count = 0

        best = None
        best_score = -1
        for index in range(count):
            item = inputs.nth(index)
            try:
                if not item.is_visible():
                    continue
                attrs = " ".join(
                    clean(item.get_attribute(name))
                    for name in ("placeholder", "aria-label", "name", "id", "title")
                ).lower()
            except Exception:
                continue
            score = 0
            if "tracking" in attrs:
                score += 6
            if "track" in attrs:
                score += 4
            if "search" in attrs:
                score += 2
            if score > best_score:
                best, best_score = item, score

        if best is None or best_score <= 0:
            return False
        try:
            best.fill(tracking)
            best.press("Enter")
            return True
        except Exception:
            return False

    def check_one(self, tracking, carrier):
        result = _base_result(tracking, carrier)
        if not valid_tracking_identifier(tracking):
            result.update(
                status="INVALID TRACKING",
                error="Tracking number is blank, malformed, or scientific notation.",
            )
            return _finish(result)
        if carrier not in SUPPORTED:
            result.update(status="UNSUPPORTED", error="Only UPS, FedEx and USPS are supported.")
            return _finish(result)

        url = build_tracking_url(carrier, tracking)
        try:
            self._page.goto(url, wait_until="domcontentloaded")
            result = self._wait_for_status(carrier, tracking)
            result["trackingUrl"] = url
            if result["status"] != "MANUAL CHECK REQUIRED":
                return result

            # One fallback: open the carrier's public tracking page and type the number.
            base_urls = {
                "UPS": "https://www.ups.com/track?loc=en_US",
                "FedEx": "https://www.fedex.com/en-us/tracking.html",
                "USPS": "https://tools.usps.com/go/TrackConfirmAction_input.action",
            }
            self._page.goto(base_urls[carrier], wait_until="domcontentloaded")
            if self._fill_tracking_input(tracking):
                result = self._wait_for_status(carrier, tracking, seconds=8.5)
                result["trackingUrl"] = url
                return result

            result["trackingUrl"] = url
            return result
        except Exception as error:
            detail = clean(str(error)).splitlines()[0][:240]
            result.update(
                status="MANUAL CHECK REQUIRED",
                error=(
                    f"Carrier page could not be read automatically ({error.__class__.__name__})"
                    + (f": {detail}" if detail else ".")
                ),
            )
            return _finish(result)

    def check_all(self, requests_to_check):
        results = {}
        if not requests_to_check:
            return results

        self.start()
        try:
            total = len(requests_to_check)
            for index, item in enumerate(requests_to_check, 1):
                tracking = item["tracking"]
                carrier = item["carrier"]
                self.progress(
                    {
                        "message": f"Carrier website {index} of {total}: {carrier} {tracking}",
                        "section": "Carrier websites",
                        "currentPage": index,
                        "totalPages": total,
                    }
                )
                results[tracking] = self.check_one(tracking, carrier)
                # Be polite to public tracking sites and reduce accidental rate limiting.
                if index < total:
                    time.sleep(0.8)
        finally:
            self.close()
        return results


def _shipping_warning(row):
    print_check = clean(row.get("printCheck"))
    carrier_status = clean(row.get("carrierStatus"))
    notified = clean(row.get("marketplaceNotified")).lower() == "notified"

    if carrier_status == "LABEL CREATED" and print_check == "NOT PRINTED":
        return "CRITICAL - NOT PRINTED AND NO CARRIER ACCEPTANCE"
    if carrier_status == "LABEL CREATED" and notified:
        return "MARKETPLACE NOTIFIED BUT NO CARRIER ACCEPTANCE"
    if carrier_status == "LABEL CREATED" and print_check == "PRINTED":
        return "PRINTED BUT NO CARRIER ACCEPTANCE"
    if print_check == "NOT PRINTED" and row.get("carrierAccepted") == "Yes":
        return "PRINT STATUS DISCREPANCY - CARRIER HAS PACKAGE"
    if carrier_status == "EXCEPTION":return "CARRIER EXCEPTION - REVIEW"
    if carrier_status == "CANCELLED":
        return "SHIPMENT CANCELLED - REVIEW"
    if carrier_status == "MANUAL CHECK REQUIRED":
        return "MANUAL CARRIER CHECK REQUIRED"
    if carrier_status == "INVALID TRACKING":
        return "INVALID TRACKING - REVIEW"
    if carrier_status == "UNSUPPORTED":
        return "UNSUPPORTED CARRIER"
    if carrier_status in ("CARRIER ACCEPTED", "IN TRANSIT", "OUT FOR DELIVERY", "DELIVERED"):
        return "OK - CARRIER ACCEPTED"
    if carrier_status == "UNKNOWN":
        return "UNKNOWN CARRIER STATUS - REVIEW"
    return ""


def add_carrier_tracking(report, progress=lambda message: None, visible_browser=True, browser_factory=None):
    unique = {}
    for row in report.get("rows", []):
        for tracking in split_tracking(row.get("tracking")):
            tracking = tracking.replace(" ", "")
            carrier = normalize_carrier(
                row.get("carrier"), row.get("service"), row.get("fulfillmentProvider"), tracking
            )
            unique.setdefault(tracking, {"tracking": tracking, "carrier": carrier})

    browser_factory = browser_factory or PublicTrackingBrowser
    tracker = browser_factory(progress=progress, visible=visible_browser)
    carrier_results = tracker.check_all(list(unique.values()))

    for row in report.get("rows", []):
        trackings = [t.replace(" ", "") for t in split_tracking(row.get("tracking"))]
        row_results = [carrier_results.get(t) for t in trackings]
        row_results = [r for r in row_results if r]
        if not row_results:
            row.update(
                normalizedCarrier="",
                trackingUrl="",
                carrierStatus="",
                carrierStatusDescription="",
                carrierAccepted="Unknown",
                firstCarrierScan="",
                latestCarrierScan="",
                latestCarrierLocation="",
                estimatedDelivery="",
                actualDelivery="",
                trackingCheckedAt="",
                carrierCheckError="",
                shippingWarning="NO TRACKING TO CHECK" if not clean(row.get("tracking")) else "",
            )
            continue

        row["normalizedCarrier"] = "; ".join(dict.fromkeys(r["carrier"] for r in row_results))
        row["trackingUrl"] = "; ".join(dict.fromkeys(r["trackingUrl"] for r in row_results if r["trackingUrl"]))
        row["carrierStatus"] = "; ".join(dict.fromkeys(r["status"] for r in row_results))
        row["carrierStatusDescription"] = "; ".join(
            dict.fromkeys(r["statusDescription"] for r in row_results if r["statusDescription"])
        )
        accepted = [r["carrierAccepted"] for r in row_results]
        row["carrierAccepted"] = (
            "Yes" if accepted and all(x == "Yes" for x in accepted)
            else ("No" if any(x == "No" for x in accepted) else "Unknown")
        )
        row["firstCarrierScan"] = "; ".join(
            dict.fromkeys(r["firstCarrierScan"] for r in row_results if r["firstCarrierScan"])
        )
        row["latestCarrierScan"] = "; ".join(
            dict.fromkeys(r["latestScan"] for r in row_results if r["latestScan"])
        )
        row["latestCarrierLocation"] = "; ".join(
            dict.fromkeys(r["latestLocation"] for r in row_results if r["latestLocation"])
        )
        row["estimatedDelivery"] = "; ".join(
            dict.fromkeys(r["estimatedDelivery"] for r in row_results if r["estimatedDelivery"])
        )
        row["actualDelivery"] = "; ".join(
            dict.fromkeys(r["actualDelivery"] for r in row_results if r["actualDelivery"])
        )
        row["trackingCheckedAt"] = "; ".join(
            dict.fromkeys(r["checkedAt"] for r in row_results if r["checkedAt"])
        )
        row["carrierCheckError"] = "; ".join(
            dict.fromkeys(r["error"] for r in row_results if r["error"])
        )
        row["shippingWarning"] = _shipping_warning(row)

    for event in report.get("events", []):
        trackings = [t.replace(" ", "") for t in split_tracking(event.get("tracking"))]
        event_results = [carrier_results.get(t) for t in trackings]
        event_results = [r for r in event_results if r]
        event["carrierStatus"] = "; ".join(dict.fromkeys(r["status"] for r in event_results))
        event["carrierAccepted"] = (
            "Yes" if event_results and all(r["carrierAccepted"] == "Yes" for r in event_results)
            else ("No" if any(r["carrierAccepted"] == "No" for r in event_results) else "Unknown")
        )

    report["carrierTracking"] = list(carrier_results.values())
    report["carrierCheckEnabled"] = True
    report["carrierCheckCount"] = len(carrier_results)
    report["carrierAcceptedCount"] = sum(1 for r in carrier_results.values() if r["carrierAccepted"] == "Yes")
    report["carrierNotAcceptedCount"] = sum(1 for r in carrier_results.values() if r["carrierAccepted"] == "No")
    report["carrierManualCount"] = sum(
        1 for r in carrier_results.values() if r["status"] == "MANUAL CHECK REQUIRED"
    )
    report["carrierErrorCount"] = sum(
        1 for r in carrier_results.values() if r["status"] in ("INVALID TRACKING", "MANUAL CHECK REQUIRED")
    )
    return report


def mark_carrier_check_disabled(report):
    for row in report.get("rows", []):
        trackings = split_tracking(row.get("tracking"))
        carrier = normalize_carrier(
            row.get("carrier"), row.get("service"), row.get("fulfillmentProvider"),
            trackings[0] if trackings else "",
        )
        url = build_tracking_url(carrier, trackings[0]) if len(trackings) == 1 and carrier in SUPPORTED else ""
        row.update(
            normalizedCarrier="",
            trackingUrl=url,
            carrierStatus="NOT CHECKED",
            carrierStatusDescription="",
            carrierAccepted="Unknown",
            firstCarrierScan="",
            latestCarrierScan="",
            latestCarrierLocation="",
            estimatedDelivery="",
            actualDelivery="",
            trackingCheckedAt="",
            carrierCheckError="",
            shippingWarning="",
        )
    for event in report.get("events", []):
        event.update(carrierStatus="NOT CHECKED", carrierAccepted="Unknown")
    report.update(
        carrierTracking=[],
        carrierCheckEnabled=False,
        carrierCheckCount=0,
        carrierAcceptedCount=0,
        carrierNotAcceptedCount=0,
        carrierManualCount=0,
        carrierErrorCount=0,
    )
    return report
