
"""Local Python web app. Run with START.cmd or python app.py."""

from __future__ import annotations

import argparse
import atexit
import base64
import json
import mimetypes
import os
from pathlib import Path
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from excel_export import build_excel, build_print_capture_excel
from shipstation import ReportError, extract_report, parse_credentials, parse_ship_date
from shipstation_ui import ShipStationBrowserManager, merge_shipstation_capture

ROOT = Path(__file__).resolve().parent
BROWSER_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
}


""" ----------- 1 - START THE LOCAL WEBSITE ----------- """


def make_server(port=8787, root=None, extractor=extract_report):
    public_folder = Path(root or ROOT / "public").resolve()
    export_lock = threading.Lock()
    shipstation_browser = ShipStationBrowserManager()
    latest_capture = {"data": None}
    atexit.register(shipstation_browser.close)

    class BrowserRequestHandler(BaseHTTPRequestHandler):
        # Silence default URL logging and keep credentials/customer data out of logs.
        def log_message(self, format, *args):
            pass

        @property
        def origin(self):
            return f"http://127.0.0.1:{self.server.server_port}"

        def headers_ok(self):
            return self.headers.get("Host") == urlsplit(self.origin).netloc

        def reply(self, status, content, content_type="application/json"):
            if isinstance(content, dict):
                content = json.dumps(content).encode()
            self.send_response(status)
            for key, value in BROWSER_SECURITY_HEADERS.items():
                self.send_header(key, value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)

        def do_GET(self):
            if not self.headers_ok():
                self.reply(403, {"error": "Open the displayed 127.0.0.1 address."})
                return
            path = unquote(urlsplit(self.path).path)
            requested_file = (
                public_folder / ("local/index.html" if path == "/" else path.lstrip("/"))
            ).resolve()
            if not requested_file.is_relative_to(public_folder) or not requested_file.is_file():
                self.reply(404, {"error": "Not found."})
                return
            content_type = {
                ".js": "text/javascript",
                ".css": "text/css",
                ".html": "text/html; charset=utf-8",
            }.get(requested_file.suffix)
            self.reply(
                200,
                requested_file.read_bytes(),
                content_type
                or mimetypes.guess_type(requested_file.name)[0]
                or "application/octet-stream",
            )

        do_HEAD = do_GET

        def do_POST(self):
            if (
                not self.headers_ok()
                or self.headers.get("Origin", self.origin) != self.origin
                or self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none")
            ):
                self.reply(403, {"error": "Open this app directly to continue."})
                return
            request_path = urlsplit(self.path).path

            if request_path == "/api/exit":
                try:
                    shipstation_browser.close()
                except Exception:
                    pass
                self.reply(200, {"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            if request_path == "/api/shipstation/open":
                try:
                    result = shipstation_browser.call("open")
                    self.reply(200, result)
                except Exception as error:
                    self.reply(500, {"error": str(error)})
                return

            if request_path == "/api/shipstation/read":
                if not export_lock.acquire(blocking=False):
                    self.reply(409, {"error": "Another read/export is already running."})
                    return
                try:
                    result = shipstation_browser.call("read", max_pages=100)
                    latest_capture["data"] = result
                    self.reply(
                        200,
                        {
                            "rowCount": result["rowCount"],
                            "printedCount": result["printedCount"],
                            "printedMissingTimeCount": result["printedMissingTimeCount"],
                            "unreadableCount": result["unreadableCount"],
                            "printedMissingTrackingCount": result["printedMissingTrackingCount"],
                            "capturedAt": result["capturedAt"],
                            "pagesRead": len(result.get("pages") or []),
                            "url": result.get("url", ""),
                        },
                    )
                except Exception as error:
                    self.reply(500, {"error": str(error)})
                finally:
                    export_lock.release()
                return

            if request_path == "/api/shipstation/capture-excel":
                capture = latest_capture.get("data")
                if not capture:
                    self.reply(400, {"error": "Read the ShipStation Shipments grid first."})
                    return
                try:
                    workbook = build_print_capture_excel(capture)
                    self.reply(
                        200,
                        {
                            "fileBase64": base64.b64encode(workbook).decode("ascii"),
                            "rowCount": capture["rowCount"],
                        },
                    )
                except Exception as error:
                    self.reply(500, {"error": str(error)})
                return

            if request_path != "/api/report":
                self.reply(404, {"error": "Not found."})
                return
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self.reply(415, {"error": "Expected a JSON request."})
                return
            payload = {}
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 24000 or self.headers.get("Transfer-Encoding"):
                    raise ReportError("Choose a TXT key file smaller than 16 KB.")
                self.connection.settimeout(30)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError()
                parse_credentials(payload.get("credentialsText"))
                parse_ship_date(payload.get("shipDate"))
            except (ValueError, TypeError, ReportError, OSError) as error:
                self.reply(
                    400,
                    {
                        "error": (
                            str(error)
                            if isinstance(error, ReportError)
                            else "Choose a valid TXT key file and Ship Date (MM/DD/YYYY)."
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
                        (json.dumps(event, ensure_ascii=True, allow_nan=False) + "\n").encode()
                    )
                    self.wfile.flush()

                def progress(update):
                    if isinstance(update, dict):
                        send({"type": "progress", **update})
                    else:
                        send({"type": "progress", "message": str(update)})

                try:
                    report = extractor(
                        payload["credentialsText"], payload["shipDate"], progress=progress
                    )
                    payload["credentialsText"] = ""
                    capture = latest_capture.get("data")
                    if capture:
                        progress("Matching ShipStation Label Printed status to shipment/tracking records...")
                        match_summary = merge_shipstation_capture(report["rows"], capture["rows"])
                        report["shipstationPrintCapture"] = capture
                        report["shipstationPrintMatchSummary"] = match_summary
                    else:
                        report["shipstationPrintCapture"] = None
                        report["shipstationPrintMatchSummary"] = {
                            "matched": 0,
                            "ambiguous": 0,
                            "missing": len(report["rows"]),
                        }
                        for row in report["rows"]:
                            row.update(
                                shipstationPrintStatus="Could not read",
                                shipstationDisplayedPrintTime="",
                                shipstationLabelPrintedRaw="",
                                shipstationPrintMatch="No UI capture",
                                shipstationPrintCapturedAt="",
                            )
                    send({"type": "progress", "message": "Creating Excel with Python..."})
                    workbook = build_excel(report)
                    summary = {
                        key: report[key]
                        for key in (
                            "version",
                            "shipDate",
                            "rowCount",
                            "missingTrackingCount",
                            "printJobCount",
                            "printHistoryAvailable",
                        )
                    }
                    summary["shipstationPrintMatched"] = report["shipstationPrintMatchSummary"]["matched"]
                    summary["shipstationPrintCaptured"] = bool(capture)
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
                                    else "The export could not be completed. No partial file was created."
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
            # Never dump an exception containing a request or customer record.
            pass

    return LocalServer(("127.0.0.1", port), BrowserRequestHandler)


""" ----------- 2 - OPEN THE PROGRAM IN THE BROWSER ----------- """


def main():
    parser = argparse.ArgumentParser(description="ShipStation Daily Shipment Check — Python")
    parser.add_argument(
        "--no-browser", action="store_true", help="Do not open the browser automatically"
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("SHIPSTATION_EXPORT_PORT", "8787"))
    )
    args = parser.parse_args()
    try:
        server = make_server(args.port)
    except OSError:
        print(
            "Cannot start the app. Close any older copy using port 8787, or choose another port with --port."
        )
        return 1
    origin = f"http://127.0.0.1:{server.server_port}"
    print(
        f"\nShipStation Daily Shipment Check — Python\nOpen {origin}\nKeep this window open. Press Ctrl+C to stop.\n"
    )
    if not args.no_browser:
        timer = threading.Timer(0.5, lambda: webbrowser.open(origin))
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.RequestHandlerClass  # keep server alive until browser cleanup below
        except Exception:
            pass
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
