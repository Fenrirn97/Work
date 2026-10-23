"""Local Windows-friendly web app for ShipStation daily shipment checks.

Version 0.4.7 deliberately keeps the old working v0.4.x workflow. ShipStation opens
in the user's normal browser session; the program does not launch a separate automated
ShipStation browser. An optional browser extension captures the Shipments -> Label
Printed cell and sends only those visible shipment fields back to this local app.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from carrier_tracking import add_carrier_tracking, mark_carrier_check_disabled
from excel_export import build_excel
from print_capture import (
    mark_no_shipstation_print_capture,
    merge_capture_store,
    merge_shipstation_print_capture,
    normalize_capture_rows,
)
from print_status import mark_no_print_csv, merge_print_status, parse_print_status_csv
from shipstation import ReportError, extract_report, parse_credentials, parse_ship_date_range

ROOT = Path(__file__).resolve().parent
SHIPSTATION_SHIPPED_URL = "https://ship.shipstation.com/shipments/shipped"
EXTENSION_FOLDER = ROOT / "ShipStation_Print_Time_Extension"
MAX_REQUEST_BYTES = 30 * 1024 * 1024
MAX_CAPTURE_BYTES = 5 * 1024 * 1024
BROWSER_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
}


def make_server(port=8787, root=None, extractor=extract_report):
    public_folder = Path(root or ROOT / "public").resolve()
    export_lock = threading.Lock()
    capture_lock = threading.Lock()
    capture_rows: list[dict] = []
    capture_token = secrets.token_urlsafe(32)

    class BrowserRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        @property
        def origin(self):
            return f"http://127.0.0.1:{self.server.server_port}"

        def headers_ok(self):
            return self.headers.get("Host") == urlsplit(self.origin).netloc

        def reply(self, status, content, content_type="application/json"):
            if isinstance(content, dict):
                content = json.dumps(content).encode("utf-8")
            self.send_response(status)
            for key, value in BROWSER_SECURITY_HEADERS.items():
                self.send_header(key, value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)

        def _read_json(self, maximum=MAX_REQUEST_BYTES):
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise ReportError("Expected a JSON request.")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ReportError("Invalid request size.") from None
            if not 1 <= length <= maximum or self.headers.get("Transfer-Encoding"):
                raise ReportError("The request is too large.")
            self.connection.settimeout(60)
            try:
                data = json.loads(self.rfile.read(length))
            except (ValueError, OSError):
                raise ReportError("Invalid JSON request.") from None
            if not isinstance(data, dict):
                raise ReportError("Invalid JSON request.")
            return data

        def do_GET(self):
            if not self.headers_ok():
                self.reply(403, {"error": "Open the displayed 127.0.0.1 address."})
                return

            path = unquote(urlsplit(self.path).path)
            if path == "/api/extension-token":
                # Edge/Chrome extension pages with localhost host permission can read this.
                self.reply(200, {"token": capture_token, "port": self.server.server_port})
                return
            if path == "/api/print-capture-status":
                with capture_lock:
                    snapshot = list(capture_rows)
                latest = max((str(row.get("capturedAt") or "") for row in snapshot), default="")
                self.reply(200, {"count": len(snapshot), "latestCapturedAt": latest})
                return

            requested_file = (
                public_folder / ("local/index.html" if path == "/" else path.lstrip("/"))
            ).resolve()
            if not requested_file.is_relative_to(public_folder) or not requested_file.is_file():
                self.reply(404, {"error": "Not found."})
                return
            content_type = {
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".html": "text/html; charset=utf-8",
                ".svg": "image/svg+xml",
            }.get(requested_file.suffix)
            self.reply(
                200,
                requested_file.read_bytes(),
                content_type or mimetypes.guess_type(requested_file.name)[0] or "application/octet-stream",
            )

        do_HEAD = do_GET

        def do_POST(self):
            request_path = urlsplit(self.path).path

            # Extension capture is intentionally the only cross-origin POST. It requires
            # a random token obtained from this running local app, preventing ordinary
            # websites from injecting fake shipment data into the report.
            if request_path == "/api/shipstation-print-capture":
                if not self.headers_ok() or self.headers.get("X-ShipStation-Capture-Token") != capture_token:
                    self.reply(403, {"error": "Print-capture token rejected. Keep the local program open and try again."})
                    return
                try:
                    payload = self._read_json(MAX_CAPTURE_BYTES)
                    normalized = normalize_capture_rows(payload.get("rows"), payload.get("capturedAt"))
                    if not normalized:
                        raise ReportError("No ShipStation shipment rows were captured.")
                    with capture_lock:
                        capture_rows[:] = merge_capture_store(capture_rows, normalized)
                        total = len(capture_rows)
                    self.reply(200, {"ok": True, "received": len(normalized), "total": total})
                except ReportError as error:
                    self.reply(400, {"error": str(error)})
                return

            if (
                not self.headers_ok()
                or self.headers.get("Origin", self.origin) != self.origin
                or self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none")
            ):
                self.reply(403, {"error": "Open this app directly at the displayed local address."})
                return

            if request_path == "/api/exit":
                self.reply(200, {"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            if request_path == "/api/open-shipstation":
                opened = webbrowser.open(SHIPSTATION_SHIPPED_URL, new=2)
                self.reply(
                    200,
                    {
                        "opened": bool(opened),
                        "url": SHIPSTATION_SHIPPED_URL,
                        "message": "ShipStation opened in your normal browser. Select the date/shipments, then export Current View and/or use the Print Time Capture extension.",
                    },
                )
                return

            if request_path == "/api/open-extension-folder":
                try:
                    if os.name == "nt":
                        os.startfile(str(EXTENSION_FOLDER))  # type: ignore[attr-defined]
                        self.reply(200, {"opened": True})
                    else:
                        self.reply(400, {"error": "Open the ShipStation_Print_Time_Extension folder manually."})
                except OSError:
                    self.reply(400, {"error": "Could not open the extension folder. Open ShipStation_Print_Time_Extension manually."})
                return

            if request_path == "/api/clear-print-capture":
                with capture_lock:
                    capture_rows.clear()
                self.reply(200, {"ok": True, "count": 0})
                return

            if request_path != "/api/report":
                self.reply(404, {"error": "Not found."})
                return

            payload = {}
            try:
                payload = self._read_json(MAX_REQUEST_BYTES)
                parse_credentials(payload.get("credentialsText"))
                payload["shipDateStart"] = payload.get("shipDateStart") or payload.get("shipDate")
                parse_ship_date_range(payload["shipDateStart"], payload.get("shipDateEnd"))
                if payload.get("printCsvText"):
                    parse_print_status_csv(payload["printCsvText"])
            except (TypeError, ReportError, OSError) as error:
                self.reply(
                    400,
                    {
                        "error": (
                            str(error)
                            if isinstance(error, ReportError)
                            else "Choose valid files and real From / Through dates."
                        )
                    },
                )
                return

            if not export_lock.acquire(blocking=False):
                self.reply(409, {"error": "An export is already running. Wait for it to finish."})
                return

            try:
                self.send_response(200)
                for key, value in BROWSER_SECURITY_HEADERS.items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Connection", "close")
                self.end_headers()

                def send(event):
                    self.wfile.write(
                        (json.dumps(event, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
                    )
                    self.wfile.flush()

                def progress(update):
                    if isinstance(update, dict):
                        send({"type": "progress", **update})
                    else:
                        send({"type": "progress", "message": str(update)})

                try:
                    report = extractor(payload["credentialsText"], payload["shipDateStart"],
                                       ship_date_end=payload.get("shipDateEnd"), progress=progress)
                    payload["credentialsText"] = ""

                    # Preserve the old v0.4.x CSV comparison exactly as the first print check.
                    print_csv_text = payload.get("printCsvText") or ""
                    if print_csv_text.strip():
                        progress("Matching the selected ShipStation Print Status CSV...")
                        records = parse_print_status_csv(print_csv_text)
                        merge_print_status(report, records)
                    else:
                        mark_no_print_csv(report)
                    payload["printCsvText"] = ""

                    # Add the exact Shipments-grid Label Printed state/time only when the
                    # user captured it from their normal logged-in browser.
                    with capture_lock:
                        captured = [dict(row) for row in capture_rows]
                    if captured:
                        progress("Matching ShipStation Label Printed date/time capture...")
                        merge_shipstation_print_capture(report, captured)
                    else:
                        mark_no_shipstation_print_capture(report)

                    if payload.get("checkCarriers"):
                        progress("Opening carrier tracking pages in Microsoft Edge / Chrome...")
                        add_carrier_tracking(
                            report,
                            progress=progress,
                            visible_browser=bool(payload.get("showCarrierBrowser", True)),
                        )
                    else:
                        mark_carrier_check_disabled(report)

                    progress("Creating the combined Excel report...")
                    workbook = build_excel(report)
                    summary = {
                        key: report.get(key)
                        for key in (
                            "version",
                            "shipDate",
                            "shipDateStart",
                            "shipDateEnd",
                            "displayDate",
                            "rangeDays",
                            "fileRange",
                            "rowCount",
                            "recordCount",
                            "missingTrackingCount",
                            "printCsvRecordCount",
                            "notPrintedRowCount",
                            "uiPrintCaptureCount",
                            "uiPrintMatchedRows",
                            "uiPrintAmbiguousRows",
                            "uiPrintedMissingTimeCount",
                            "printedMissingTrackingCount",
                            "carrierCheckCount",
                            "carrierAcceptedCount",
                            "carrierNotAcceptedCount",
                            "carrierManualCount",
                            "carrierErrorCount",
                        )
                    }
                    summary["fileBase64"] = base64.b64encode(workbook).decode("ascii")
                    send({"type": "complete", "report": summary})
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass
                except Exception as error:
                    try:
                        send(
                            {
                                "type": "error",
                                "message": (
                                    str(error)
                                    if isinstance(error, ReportError)
                                    else "The report could not be completed. No partial Excel file was created."
                                ),
                            }
                        )
                    except OSError:
                        pass
            finally:
                payload.clear()
                export_lock.release()
                self.close_connection = True

    class LocalServer(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            pass

    return LocalServer(("127.0.0.1", port), BrowserRequestHandler)


def main():
    parser = argparse.ArgumentParser(description="ShipStation Daily Shipment Check v0.4.7")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SHIPSTATION_CHECK_PORT", "8787")))
    args = parser.parse_args()

    try:
        server = make_server(args.port)
    except OSError:
        print("Cannot start the app. Close any older copy using port 8787, then try again.")
        return 1

    origin = f"http://127.0.0.1:{server.server_port}"
    print(
        "\nShipStation Daily Shipment Check v0.4.7\n"
        f"Open {origin}\n"
        "Keep this window open while the program is running.\n"
        "This build uses the old v0.4.x ShipStation workflow and your normal browser session.\n"
    )
    if not args.no_browser:
        timer = threading.Timer(0.6, lambda: webbrowser.open(origin))
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
