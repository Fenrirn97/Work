"""Read ShipStation's Shipments grid with a dedicated persistent Edge profile.

The Shipments -> Label Printed cell is treated as the authoritative ShipStation UI
source. The module never guesses a print time from label creation, Ship Date, or the
Windows print spooler.
"""

from __future__ import annotations

import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PRINTED_RE = re.compile(r"\bprinted\b", re.I)
NOT_PRINTED_RE = re.compile(r"\b(?:not\s+printed|unprinted)\b", re.I)
CREATED_RE = re.compile(r"\bcreated\b", re.I)
SHIPSTATION_LOGIN_URL = "https://ss6.shipstation.com/login"
SHIPSTATION_HOME_URL = "https://ss6.shipstation.com/"

DATE_TIME_PATTERNS = [
    re.compile(
        r"\b\d{1,2}/\d{1,2}/\d{2,4}(?:,)?(?:\s+at)?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b",
        re.I,
    ),
    re.compile(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}(?:,)?(?:\s+at)?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b",
        re.I,
    ),
    re.compile(
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}(?:,)?(?:\s+at)?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b",
        re.I,
    ),
]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_label_print_cell(raw_text: str) -> dict[str, str]:
    """Interpret only what the ShipStation cell actually exposes."""
    raw = clean_text(raw_text)
    lower = raw.lower()
    if not raw:
        status = "Could not read"
    elif NOT_PRINTED_RE.search(raw):
        status = "Not Printed"
    elif PRINTED_RE.search(raw):
        status = "Printed"
    elif CREATED_RE.search(raw):
        status = "Created - not printed"
    elif lower in {"yes", "true"}:
        status = "Printed"
    elif lower in {"no", "false"}:
        status = "Not Printed"
    else:
        status = "Could not read"

    displayed_time = ""
    for pattern in DATE_TIME_PATTERNS:
        match = pattern.search(raw)
        if match:
            displayed_time = clean_text(match.group(0)).replace(" at ", " ")
            break

    return {
        "printStatus": status,
        "displayedPrintTime": displayed_time,
        "rawLabelPrinted": raw,
    }


def split_values(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*;\s*|\s*,\s*", text) if part.strip()]


def _norm_identifier(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", clean_text(value).upper())


def merge_shipstation_capture(report_rows: list[dict], capture_rows: list[dict]) -> dict[str, int]:
    """Attach ShipStation UI print status by shipment number first, then tracking.

    An order number alone is intentionally not used as an automatic match because one
    order can have multiple shipments/packages.
    """
    by_shipment: dict[str, list[dict]] = {}
    by_tracking: dict[str, list[dict]] = {}
    by_order: dict[str, list[dict]] = {}
    for captured in capture_rows:
        shipment = _norm_identifier(captured.get("shipmentNumber"))
        tracking = _norm_identifier(captured.get("tracking"))
        if shipment:
            by_shipment.setdefault(shipment, []).append(captured)
        if tracking:
            by_tracking.setdefault(tracking, []).append(captured)
        order = _norm_identifier(captured.get("orderNumber"))
        if order:
            by_order.setdefault(order, []).append(captured)

    # Order-number fallback is allowed only when both sides prove that the order has
    # exactly one shipment/package. This avoids linking the wrong package on split orders.
    report_order_packages: dict[str, set[tuple[str, str]]] = {}
    for report_row in report_rows:
        order = _norm_identifier(report_row.get("orderNumber"))
        if not order:
            continue
        report_order_packages.setdefault(order, set()).add(
            (
                _norm_identifier(report_row.get("shipmentIds")),
                _norm_identifier(report_row.get("tracking")),
            )
        )

    matched = ambiguous = missing = 0
    for row in report_rows:
        candidates: list[dict] = []
        match_type = ""
        for shipment in split_values(row.get("shipmentIds")):
            found = by_shipment.get(_norm_identifier(shipment), [])
            if found:
                candidates.extend(found)
                match_type = "Shipment #"
        if not candidates:
            for tracking in split_values(row.get("tracking")):
                found = by_tracking.get(_norm_identifier(tracking), [])
                if found:
                    candidates.extend(found)
                    match_type = "Tracking #"
        if not candidates:
            order_key = _norm_identifier(row.get("orderNumber"))
            captured_for_order = by_order.get(order_key, []) if order_key else []
            unique_capture_shipments = {
                (
                    _norm_identifier(item.get("shipmentNumber")),
                    _norm_identifier(item.get("tracking")),
                )
                for item in captured_for_order
            }
            if (
                order_key
                and len(report_order_packages.get(order_key, set())) == 1
                and len(unique_capture_shipments) == 1
                and captured_for_order
            ):
                candidates.extend(captured_for_order)
                match_type = "Order # (unique shipment only)"

        unique: list[dict] = []
        seen = set()
        for item in candidates:
            key = (
                _norm_identifier(item.get("shipmentNumber")),
                _norm_identifier(item.get("tracking")),
                clean_text(item.get("rawLabelPrinted")),
            )
            if key not in seen:
                seen.add(key)
                unique.append(item)

        row.update(
            shipstationPrintStatus="Could not read",
            shipstationDisplayedPrintTime="",
            shipstationLabelPrintedRaw="",
            shipstationPrintMatch="No UI match",
            shipstationPrintCapturedAt="",
        )
        notes = [n.strip() for n in str(row.get("warnings") or "").split(";") if n.strip()]

        if len(unique) == 1:
            item = unique[0]
            row["shipstationPrintStatus"] = item.get("printStatus") or "Could not read"
            row["shipstationDisplayedPrintTime"] = item.get("displayedPrintTime") or ""
            row["shipstationLabelPrintedRaw"] = item.get("rawLabelPrinted") or ""
            row["shipstationPrintMatch"] = match_type
            row["shipstationPrintCapturedAt"] = item.get("capturedAt") or ""
            matched += 1
            if row["shipstationPrintStatus"] == "Printed" and not clean_text(row.get("tracking")):
                notes.append("CRITICAL: ShipStation says Printed but tracking number is missing")
            if row["shipstationPrintStatus"] == "Printed" and not row["shipstationDisplayedPrintTime"]:
                notes.append("ShipStation says Printed but displayed print date/time could not be read")
        elif len(unique) > 1:
            ambiguous += 1
            row["shipstationPrintMatch"] = "Ambiguous"
            notes.append("Multiple ShipStation UI rows matched this shipment; print status not guessed")
        else:
            missing += 1
            notes.append("ShipStation Label Printed cell was not matched from the Shipments grid")

        row["warnings"] = "; ".join(dict.fromkeys(notes))

    return {"matched": matched, "ambiguous": ambiguous, "missing": missing}


GRID_EXTRACTOR_JS = r"""
async () => {
  const visible = (el) => {
    if (!el) return false;
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const text = (el) => {
    if (!el) return '';
    const pieces = [
      el.innerText,
      el.textContent,
      el.getAttribute && el.getAttribute('aria-label'),
      el.getAttribute && el.getAttribute('title'),
      el.getAttribute && el.getAttribute('data-tooltip-content'),
      el.getAttribute && el.getAttribute('data-original-title')
    ];
    if (el.querySelectorAll) {
      for (const child of el.querySelectorAll('[aria-label],[title],[data-tooltip-content],[data-original-title],time')) {
        pieces.push(child.innerText, child.textContent, child.getAttribute('aria-label'), child.getAttribute('title'), child.getAttribute('data-tooltip-content'), child.getAttribute('data-original-title'), child.getAttribute('datetime'));
      }
    }
    return [...new Set(pieces.filter(Boolean).map(x => String(x).replace(/\s+/g,' ').trim()).filter(Boolean))].join(' | ');
  };
  const norm = (s) => String(s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const headerEls = [...document.querySelectorAll('[role="columnheader"], thead th')].filter(visible);
  if (!headerEls.length) return {ok:false, reason:'No visible column headers found', headers:[]};

  const groups = new Map();
  for (const h of headerEls) {
    let root = h.closest('[role="grid"], [role="treegrid"], table');
    if (!root) {
      let p = h.parentElement;
      for (let i=0; p && i<8; i++, p=p.parentElement) {
        if (p.querySelectorAll('[role="row"], tbody tr').length > 1) { root = p; break; }
      }
    }
    if (!root) continue;
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(h);
  }

  const aliases = {
    shipment: ['shipment #','shipment number','shipment'],
    tracking: ['tracking #','tracking number','tracking'],
    order: ['order #','order number','order'],
    label: ['label printed','label print','label']
  };
  const findIndex = (headers, names) => {
    for (let i=0; i<headers.length; i++) {
      const h = norm(headers[i]);
      if (names.some(n => h === n || h.includes(n))) return i;
    }
    return -1;
  };

  let chosen = null;
  for (const [root, hs] of groups.entries()) {
    const headers = hs.map(text);
    const score = (findIndex(headers, aliases.label) >= 0 ? 5 : 0) +
                  (findIndex(headers, aliases.shipment) >= 0 ? 3 : 0) +
                  (findIndex(headers, aliases.tracking) >= 0 ? 3 : 0) +
                  (findIndex(headers, aliases.order) >= 0 ? 1 : 0);
    if (!chosen || score > chosen.score) chosen = {root, hs, headers, score};
  }
  if (!chosen || chosen.score < 5) {
    return {ok:false, reason:'Could not identify the Shipments grid / Label Printed column', headers:headerEls.map(text)};
  }

  // Sort headers by aria-colindex when available, otherwise by visual X position.
  chosen.hs.sort((a,b) => {
    const ai = Number(a.getAttribute('aria-colindex') || 0);
    const bi = Number(b.getAttribute('aria-colindex') || 0);
    if (ai && bi) return ai - bi;
    return a.getBoundingClientRect().left - b.getBoundingClientRect().left;
  });
  const headers = chosen.hs.map(text);
  const idx = {
    shipment: findIndex(headers, aliases.shipment),
    tracking: findIndex(headers, aliases.tracking),
    order: findIndex(headers, aliases.order),
    label: findIndex(headers, aliases.label)
  };

  const collectVisible = async () => {
    const result = [];
    const rows = [...chosen.root.querySelectorAll('[role="row"], tbody tr')].filter(visible);
    for (const row of rows) {
      if (row.querySelector('[role="columnheader"], th')) continue;
      let cells = [...row.querySelectorAll(':scope > [role="gridcell"], :scope > td')].filter(visible);
      if (!cells.length) cells = [...row.querySelectorAll('[role="gridcell"], td')].filter(visible);
      if (!cells.length) continue;
      cells.sort((a,b) => {
        const ai = Number(a.getAttribute('aria-colindex') || 0);
        const bi = Number(b.getAttribute('aria-colindex') || 0);
        if (ai && bi) return ai - bi;
        return a.getBoundingClientRect().left - b.getBoundingClientRect().left;
      });
      const vals = cells.map(text);
      if (idx.label >= 0 && idx.label < cells.length) {
        const labelCell = cells[idx.label];
        const labelNow = vals[idx.label] || '';
        const looksPrinted = /\bprinted\b/i.test(labelNow) && !/\bnot\s+printed\b/i.test(labelNow);
        const hasDate = /\b\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}\b/.test(labelNow) ||
                        /\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}/i.test(labelNow);
        if (looksPrinted && !hasDate) {
          try {
            labelCell.dispatchEvent(new MouseEvent('mouseover', {bubbles:true, cancelable:true, view:window}));
            labelCell.dispatchEvent(new MouseEvent('mouseenter', {bubbles:false, cancelable:true, view:window}));
            await new Promise(r => setTimeout(r, 90));
            const tooltips = [...document.querySelectorAll('[role="tooltip"], .MuiTooltip-tooltip, [data-popper-placement]')]
              .filter(visible)
              .map(text)
              .filter(Boolean);
            if (tooltips.length) vals[idx.label] = [...new Set([labelNow, ...tooltips])].join(' | ');
            labelCell.dispatchEvent(new MouseEvent('mouseout', {bubbles:true, cancelable:true, view:window}));
            labelCell.dispatchEvent(new MouseEvent('mouseleave', {bubbles:false, cancelable:true, view:window}));
          } catch (_) {}
        }
      }
      const get = (i) => i >= 0 && i < vals.length ? vals[i] : '';
      const record = {
        shipmentNumber: get(idx.shipment),
        tracking: get(idx.tracking),
        orderNumber: get(idx.order),
        labelPrintedRaw: get(idx.label)
      };
      if (Object.values(record).some(Boolean)) result.push(record);
    }
    return result;
  };

  const rowsByKey = new Map();
  const addRows = async () => {
    for (const r of await collectVisible()) {
      const key = [r.shipmentNumber, r.tracking, r.orderNumber, r.labelPrintedRaw].join('||');
      rowsByKey.set(key, r);
    }
  };

  await addRows();
  const all = [chosen.root, ...chosen.root.querySelectorAll('*')];
  let scroller = all.find(el => visible(el) && el.scrollHeight > el.clientHeight + 80 && getComputedStyle(el).overflowY !== 'visible');
  if (scroller) {
    const original = scroller.scrollTop;
    const step = Math.max(200, Math.floor(scroller.clientHeight * 0.75));
    let stable = 0;
    let lastCount = rowsByKey.size;
    for (let pos=0, loops=0; pos <= scroller.scrollHeight && loops < 250; pos += step, loops++) {
      scroller.scrollTop = Math.min(pos, scroller.scrollHeight);
      await new Promise(r => setTimeout(r, 110));
      await addRows();
      if (rowsByKey.size === lastCount && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 5) stable++;
      else stable = 0;
      lastCount = rowsByKey.size;
      if (stable >= 2) break;
    }
    scroller.scrollTop = original;
    await new Promise(r => setTimeout(r, 80));
  }

  const rowCount = Number(chosen.root.getAttribute('aria-rowcount') || 0) || null;
  return {ok:true, headers, indexes:idx, rows:[...rowsByKey.values()], ariaRowCount:rowCount};
}
"""


@dataclass
class _Command:
    action: str
    payload: dict
    reply: queue.Queue


class ShipStationBrowserManager:
    """Own Playwright on one background thread so the browser can stay open."""

    def __init__(self):
        self.commands: queue.Queue[_Command] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.started = threading.Event()
        self.start_error = ""

    def _ensure_thread(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._worker, name="ShipStationBrowser", daemon=True)
        self.thread.start()
        self.started.wait(timeout=15)
        if self.start_error:
            raise RuntimeError(self.start_error)

    def call(self, action: str, **payload):
        self._ensure_thread()
        reply: queue.Queue = queue.Queue(maxsize=1)
        self.commands.put(_Command(action, payload, reply))
        result = reply.get(timeout=180)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        if not (self.thread and self.thread.is_alive()):
            return
        try:
            self.call("close")
        except Exception:
            pass

    def _worker(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            self.start_error = (
                "Browser support is not installed. Close the program and run START.cmd while connected to the internet. "
                f"({exc})"
            )
            self.started.set()
            return

        playwright = context = None
        try:
            playwright = sync_playwright().start()
            self.started.set()
            while True:
                cmd = self.commands.get()
                try:
                    if cmd.action == "close":
                        if context:
                            context.close()
                            context = None                        cmd.reply.put({"closed": True})
                        break
                    if context is None:
                        context = self._launch_context(playwright)
                    page = self._get_page(context)
                    if cmd.action == "open":
                        self._navigate_to_shipstation(page)
                        page.bring_to_front()
                        cmd.reply.put({"opened": True, "url": page.url})
                    elif cmd.action == "read":
                        cmd.reply.put(self._read_all_pages(page, cmd.payload.get("max_pages", 100)))
                    else:
                        raise RuntimeError("Unknown browser command.")
                except Exception as exc:
                    cmd.reply.put(exc)
        except Exception as exc:
            if not self.started.is_set():
                self.start_error = str(exc)
                self.started.set()
        finally:
            try:
                if context:
                    context.close()
            except Exception:
                pass
            try:
                if playwright:
                    playwright.stop()
            except Exception:
                pass

    def _profile_dir(self) -> Path:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ShipStationDailyCheck"
        path = base / "EdgeProfile"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _launch_context(self, playwright):
        profile = self._profile_dir()
        try:
            return playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                channel="msedge",
                headless=False,
                viewport=None,
                chromium_sandbox=True,
                args=["--start-maximized"],
            )
        except Exception as edge_error:
            raise RuntimeError(
                "Could not open the dedicated ShipStation Edge window. Make sure Microsoft Edge is installed. "
                f"Details: {edge_error}"
            ) from edge_error


    @staticmethod
    def _navigate_to_shipstation(page):
        """Open the real ShipStation sign-in/app page from an about:blank tab.

        Use a documented/current ShipStation login host and verify that navigation
        actually left about:blank.  A failed navigation is surfaced to the local app
        instead of silently leaving the employee staring at a blank automation window.
        """
        current = clean_text(getattr(page, "url", ""))
        if "shipstation" in current.lower() and current.lower() not in {"about:blank", "about:blank/"}:
            return

        errors = []
        for target in (SHIPSTATION_LOGIN_URL, SHIPSTATION_HOME_URL):
            try:
                page.goto(target, wait_until="commit", timeout=60000)
                page.wait_for_timeout(1000)
                current = clean_text(getattr(page, "url", ""))
                if current and not current.lower().startswith("about:blank"):
                    return
                errors.append(f"{target} stayed on {current or 'blank page'}")
            except Exception as exc:
                errors.append(f"{target}: {exc}")

        raise RuntimeError(
            "The dedicated Edge window opened, but ShipStation did not load. "
            "Check that this computer can open ShipStation normally in Edge, then try again. "
            "Navigation details: " + " | ".join(errors)
        )

    @staticmethod
    def _get_page(context):
        pages = [p for p in context.pages if not p.is_closed()]
        if pages:
            # Prefer the most recently opened ShipStation page.
            for page in reversed(pages):
                if "shipstation" in page.url.lower():
                    return page
            return pages[-1]
        return context.new_page()

    def _read_page(self, page):
        result = page.evaluate(GRID_EXTRACTOR_JS)
        if not isinstance(result, dict) or not result.get("ok"):
            headers = ", ".join((result or {}).get("headers") or [])
            reason = (result or {}).get("reason") or "Shipments grid could not be read"
            if headers:
                reason += f". Visible headers: {headers[:1000]}"
            raise RuntimeError(
                reason
                + ". In ShipStation, open Shipments > Shipments and enable the Label Printed, Shipment #, and Tracking # columns, then try again."
            )
        captured_at = datetime.now().astimezone().isoformat(timespec="seconds")
        rows = []
        for raw in result.get("rows") or []:
            parsed = parse_label_print_cell(raw.get("labelPrintedRaw", ""))
            rows.append(
                {
                    "shipmentNumber": clean_text(raw.get("shipmentNumber")),
                    "tracking": clean_text(raw.get("tracking")),
                    "orderNumber": clean_text(raw.get("orderNumber")),
                    **parsed,
                    "capturedAt": captured_at,
                }
            )
        return {
            "rows": rows,
            "headers": result.get("headers") or [],
            "ariaRowCount": result.get("ariaRowCount"),
            "capturedAt": captured_at,
        }

    @staticmethod
    def _find_next_button(page):
        selectors = [
            'button[aria-label="Next page" i]',
            'button[aria-label*="next page" i]',
            'button[title="Next page" i]',
            'button[title*="next page" i]',
            '[role="button"][aria-label*="next page" i]',
        ]
        for selector in selectors:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 10)):
                candidate = loc.nth(i)
                try:
                    if candidate.is_visible():
                        return candidate
                except Exception:
                    continue
        return None

    def _read_all_pages(self, page, max_pages: int):
        if "shipstation" not in page.url.lower():
            raise RuntimeError("The dedicated browser is not on ShipStation. Open ShipStation first.")
        all_rows: dict[tuple, dict] = {}
        page_summaries = []
        first_headers = []
        for page_number in range(1, max(1, min(int(max_pages or 100), 250)) + 1):
            data = self._read_page(page)
            first_headers = first_headers or data["headers"]
            for row in data["rows"]:
                key = (
                    _norm_identifier(row.get("shipmentNumber")),
                    _norm_identifier(row.get("tracking")),
                    clean_text(row.get("rawLabelPrinted")),
                )
                all_rows[key] = row
            page_summaries.append({"page": page_number, "rows": len(data["rows"])})

            next_button = self._find_next_button(page)
            if next_button is None:
                break
            try:
                disabled = next_button.is_disabled() or next_button.get_attribute("aria-disabled") == "true"
            except Exception:
                disabled = False
            if disabled:
                break

            before = "|".join(
                f"{r.get('shipmentNumber','')}:{r.get('tracking','')}" for r in data["rows"][:5]
            )
            next_button.click(timeout=10000)
            changed = False
            for _ in range(40):
                time.sleep(0.15)
                try:
                    probe = self._read_page(page)
                except Exception:
                    continue
                after = "|".join(
                    f"{r.get('shipmentNumber','')}:{r.get('tracking','')}" for r in probe["rows"][:5]
                )
                if after != before:
                    changed = True
                    break
            if not changed:
                # Avoid clicking indefinitely if ShipStation's pagination control changed behavior.
                break

        rows = list(all_rows.values())
        printed = sum(r.get("printStatus") == "Printed" for r in rows)
        incomplete = sum(
            r.get("printStatus") == "Printed" and not r.get("displayedPrintTime") for r in rows
        )
        unreadable = sum(r.get("printStatus") == "Could not read" for r in rows)
        missing_tracking_printed = sum(
            r.get("printStatus") == "Printed" and not clean_text(r.get("tracking")) for r in rows
        )
        return {
            "url": page.url,
            "headers": first_headers,
            "rows": rows,
            "rowCount": len(rows),
            "printedCount": printed,
            "printedMissingTimeCount": incomplete,
            "unreadableCount": unreadable,
            "printedMissingTrackingCount": missing_tracking_printed,
            "pages": page_summaries,
            "capturedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": "Print time is preserved exactly as displayed by ShipStation. It is not assumed to be first-print time.",
        }
