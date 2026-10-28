"""Amazon Data Extractor v0.6.3.2.

The web app keeps two jobs separate:
1. Live Extraction asks Bright Data for public Amazon product information.
2. Offline Compare compares a saved extraction with a Category Listings Report.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys
import tempfile
import threading


ASSET_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PROJECT_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
if (ASSET_DIR / "src").is_dir():
    sys.path.insert(0, str(ASSET_DIR / "src"))


from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from amazon_data_extractor.asin_reader import InputWorkbookError, read_asins
from amazon_data_extractor.brightdata_client import BrightDataClient, BrightDataError
from amazon_data_extractor.cli import _append_error_log
from amazon_data_extractor.catalog_reader import clean_asin
from amazon_data_extractor.comparator import prepare_comparison, write_prepared_comparison
from amazon_data_extractor.credentials import KeyConfigurationError, load_api_key
from amazon_data_extractor.exporter import write_outputs
from amazon_data_extractor.live_records import build_live_results
from amazon_data_extractor.offline_reader import (
    OfflineWorkbookError,
    read_offline_extraction,
)


APP_VERSION = "0.6.3.2"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
RUN_ID_PATTERN = re.compile(
    r"^amazon_(?:extraction|comparison)_\d{8}_\d{6}(?:_\d+)?$"
)
PENDING_EXTRACTION = "_pending_extraction.xlsx"
PENDING_CATALOG_STEM = "_pending_catalog"
PENDING_ALL_LISTINGS = "_pending_all_listings.txt"


def choose_mode(selected_mode: str, asin_count: int) -> str:
    """Automatic mode uses sync for small jobs and async for larger jobs."""
    selected_mode = (selected_mode or "Automatic").strip()
    if selected_mode == "Automatic":
        return "sync" if asin_count <= 20 else "async"
    if selected_mode == "Synchronous":
        return "sync"
    if selected_mode == "Asynchronous":
        return "async"
    raise ValueError("Unknown extraction mode.")


def new_run_directory(
    output_dir: Path,
    started_at: datetime,
    *,
    prefix: str,
) -> tuple[str, Path]:
    """Create a unique run name without overwriting an earlier run."""
    base_name = f"{prefix}_{started_at.strftime('%Y%m%d_%H%M%S')}"
    run_name = base_name
    number = 2
    while (output_dir / run_name).exists():
        run_name = f"{base_name}_{number}"
        number += 1
    return run_name, output_dir / run_name


def save_temporary_upload(upload, suffix: str) -> Path:
    """Save one browser upload temporarily so the workbook readers can open it."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        upload.save(temp_file)
        return Path(temp_file.name)


def delete_temporary_files(*paths: Path | None) -> None:
    for path in paths:
        if path is None:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def pending_catalog_path(run_dir: Path) -> Path | None:
    for suffix in (".xlsx", ".xlsm"):
        candidate = run_dir / f"{PENDING_CATALOG_STEM}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def cleanup_pending_inputs(run_dir: Path) -> None:
    """Remove staged uploads after the comparison is finished."""
    paths = [
        run_dir / PENDING_EXTRACTION,
        run_dir / PENDING_ALL_LISTINGS,
        run_dir / f"{PENDING_CATALOG_STEM}.xlsx",
        run_dir / f"{PENDING_CATALOG_STEM}.xlsm",
    ]
    delete_temporary_files(*paths)


def collect_amazon_records(
    client: BrightDataClient,
    asins: list[str],
    mode: str,
) -> list[dict]:
    if mode == "sync":
        return client.collect_sync(asins)
    snapshot_id = client.trigger_collection(asins)
    client.wait_until_ready(snapshot_id)
    return client.download_results(snapshot_id)


def extraction_preview(records: list[dict]) -> list[dict]:
    """Keep the browser preview small even when the extraction is large."""
    return [
        {
            "asin": record.get("asin") or record.get("input_asin") or "",
            "title": record.get("title") or "",
            "price": record.get("final_price") or record.get("initial_price") or "",
            "availability": record.get("availability") or "",
            "seller": record.get("seller_name") or record.get("buybox_seller") or "",
        }
        for record in records[:100]
    ]


def live_result_summary(records: list[dict], requested_asins: list[str]) -> dict:
    """Give the user a direct explanation of missing, failed, or redirected ASINs."""
    live_results = build_live_results(records, requested_asins)
    counts = {"Found": 0, "Redirected": 0, "Not Found": 0, "Extraction Failed": 0}
    problems = []
    for asin in requested_asins:
        result = live_results.get(asin)
        if result is None:
            continue
        counts[result.status] = counts.get(result.status, 0) + 1
        if result.status != "Found":
            problems.append(result)
    return {"counts": counts, "problems": problems}


def close_program() -> None:
    """End the local Flask/Python process immediately."""
    os._exit(0)


def schedule_program_exit(delay_seconds: float = 0.75) -> None:
    """Let the browser receive its final page before ending Python."""
    exit_timer = threading.Timer(delay_seconds, close_program)
    exit_timer.daemon = True
    exit_timer.start()


def create_app(config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(ASSET_DIR / "templates"),
        static_folder=str(ASSET_DIR / "static"),
    )
    app.config.update(
        SECRET_KEY=os.urandom(32),
        PROJECT_DIR=PROJECT_DIR,
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
        EXIT_SCHEDULER=schedule_program_exit,
    )
    if config:
        app.config.update(config)

    @app.context_processor
    def common_context():
        return {"version": APP_VERSION}

    @app.get("/")
    def index():
        project_dir = Path(app.config["PROJECT_DIR"])
        try:
            key_found = bool(load_api_key(project_dir))
        except KeyConfigurationError as exc:
            flash(str(exc), "error")
            key_found = False
        return render_template("index.html", key_found=key_found)

    @app.post("/extract")
    def extract():
        asin_upload = request.files.get("workbook")
        if asin_upload is None or not asin_upload.filename:
            flash("Choose an ASIN Excel workbook first.", "error")
            return redirect(url_for("index", tab="live"))

        asin_filename = secure_filename(asin_upload.filename) or "input.xlsx"
        if Path(asin_filename).suffix.lower() != ".xlsx":
            flash("The ASIN input must be an .xlsx Excel workbook.", "error")
            return redirect(url_for("index", tab="live"))

        project_dir = Path(app.config["PROJECT_DIR"])
        output_dir = project_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        asin_temp = None

        try:
            asin_temp = save_temporary_upload(asin_upload, ".xlsx")
            asin_result = read_asins(asin_temp)
            if not asin_result.asins:
                raise InputWorkbookError("No valid ASINs were found in the workbook.")

            mode = choose_mode(
                request.form.get("mode", "Automatic"),
                len(asin_result.asins),
            )
            if mode == "sync" and len(asin_result.asins) > 20:
                raise BrightDataError("Synchronous mode supports at most 20 ASINs.")

            api_key = load_api_key(project_dir)
            if not api_key:
                flash(
                    "Open brightdata_api_key.txt beside app.py, replace the placeholder "
                    "with your Bright Data account API key, save the file, and try again.",
                    "error",
                )
                return redirect(url_for("index", tab="live"))

            started_at = datetime.now(timezone.utc)
            run_name, run_dir = new_run_directory(
                output_dir,
                started_at,
                prefix="amazon_extraction",
            )
            records = collect_amazon_records(
                BrightDataClient(api_key),
                asin_result.asins,
                mode,
            )
            metadata = {
                "app_version": APP_VERSION,
                "source_workbook": asin_filename,
                "mode": mode,
                "returned_record_count": len(records),
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            raw_path, workbook_path, metadata_path = write_outputs(
                run_dir,
                records=records,
                audit_rows=asin_result.audit_rows,
                metadata=metadata,
            )
            return render_template(
                "results.html",
                run_name=run_name,
                source_workbook=asin_filename,
                sheet_name=asin_result.sheet_name,
                asin_count=len(asin_result.asins),
                invalid_count=asin_result.invalid_count,
                duplicate_count=asin_result.duplicate_count,
                mode=mode,
                record_count=len(records),
                preview=extraction_preview(records),
                live_summary=live_result_summary(records, asin_result.asins),
                workbook_name=workbook_path.name,
                raw_name=raw_path.name,
                metadata_name=metadata_path.name,
            )
        except InputWorkbookError as exc:
            flash(str(exc), "error")
            return redirect(url_for("index", tab="live"))
        except BrightDataError as exc:
            started_at = datetime.now(timezone.utc)
            run_name, _run_dir = new_run_directory(
                output_dir,
                started_at,
                prefix="amazon_extraction",
            )
            try:
                error_log = _append_error_log(
                    output_dir,
                    run_name=run_name,
                    input_file=Path(asin_filename),
                    asin_count=len(asin_result.asins) if "asin_result" in locals() else 0,
                    error=exc,
                )
                flash(f"{exc} Error log: {error_log}", "error")
            except OSError:
                flash(str(exc), "error")
            return redirect(url_for("index", tab="live"))
        except (OSError, ValueError) as exc:
            flash(f"Could not process the workbook: {exc}", "error")
            return redirect(url_for("index", tab="live"))
        finally:
            delete_temporary_files(asin_temp)

    @app.post("/compare")
    def compare_offline():
        extraction_upload = request.files.get("extraction_workbook")
        catalog_upload = request.files.get("catalog_workbook")
        all_listings_upload = request.files.get("all_listings_file")
        if extraction_upload is None or not extraction_upload.filename:
            flash("Choose amazon_extraction.xlsx first.", "error")
            return redirect(url_for("index", tab="offline"))
        if catalog_upload is None or not catalog_upload.filename:
            flash("Choose a Category Listings Report.", "error")
            return redirect(url_for("index", tab="offline"))

        extraction_filename = (
            secure_filename(extraction_upload.filename) or "amazon_extraction.xlsx"
        )
        catalog_filename = (
            secure_filename(catalog_upload.filename) or "category_listings.xlsm"
        )
        all_listings_filename = (
            secure_filename(all_listings_upload.filename)
            if all_listings_upload and all_listings_upload.filename
            else ""
        )
        if Path(extraction_filename).suffix.lower() != ".xlsx":
            flash("The saved Amazon extraction must be an .xlsx workbook.", "error")
            return redirect(url_for("index", tab="offline"))
        if Path(catalog_filename).suffix.lower() not in {".xlsx", ".xlsm"}:
            flash("The Category Listings Report must be .xlsx or .xlsm.", "error")
            return redirect(url_for("index", tab="offline"))
        if (
            all_listings_filename
            and Path(all_listings_filename).suffix.lower() not in {".txt", ".tsv"}
        ):
            flash("The optional All Listings Report must be .txt or .tsv.", "error")
            return redirect(url_for("index", tab="offline"))

        project_dir = Path(app.config["PROJECT_DIR"])
        output_dir = project_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc)
        run_name, run_dir = new_run_directory(
            output_dir,
            started_at,
            prefix="amazon_comparison",
        )
        run_dir.mkdir(parents=True, exist_ok=False)
        extraction_path = run_dir / PENDING_EXTRACTION
        catalog_path = run_dir / (
            f"{PENDING_CATALOG_STEM}{Path(catalog_filename).suffix.lower()}"
        )
        all_listings_path = (
            run_dir / PENDING_ALL_LISTINGS if all_listings_filename else None
        )

        try:
            extraction_upload.save(extraction_path)
            catalog_upload.save(catalog_path)
            if all_listings_path is not None:
                all_listings_upload.save(all_listings_path)

            offline = read_offline_extraction(extraction_path)
            prepared = prepare_comparison(
                records=offline.records,
                requested_asins=offline.requested_asins,
                catalog_path=catalog_path,
                all_listings_path=all_listings_path,
            )

            if prepared.unresolved_catalog:
                return render_template(
                    "resolve_asins.html",
                    run_name=run_name,
                    unresolved=prepared.unresolved_catalog,
                    extraction_name=extraction_filename,
                    catalog_name=catalog_filename,
                    all_listings_name=all_listings_filename,
                    automatic_stats=prepared.resolution_stats,
                    entered_values={},
                )

            comparison_path = run_dir / "comparison_report.xlsx"
            comparison_stats = write_prepared_comparison(prepared, comparison_path)
            cleanup_pending_inputs(run_dir)
            return render_template(
                "offline_results.html",
                run_name=run_name,
                extraction_name=extraction_filename,
                catalog_name=catalog_filename,
                requested_count=len(offline.requested_asins),
                record_count=len(offline.records),
                comparison_name=comparison_path.name,
                comparison_stats=comparison_stats,
            )
        except (OfflineWorkbookError, OSError, ValueError) as exc:
            cleanup_pending_inputs(run_dir)
            flash(f"Offline comparison failed: {exc}", "error")
            return redirect(url_for("index", tab="offline"))

    @app.post("/compare/<run_name>/resolve")
    def resolve_asins(run_name: str):
        if not RUN_ID_PATTERN.fullmatch(run_name):
            abort(404)

        project_dir = Path(app.config["PROJECT_DIR"])
        run_dir = project_dir / "output" / run_name
        extraction_path = run_dir / PENDING_EXTRACTION
        catalog_path = pending_catalog_path(run_dir)
        all_listings_path = run_dir / PENDING_ALL_LISTINGS
        if not extraction_path.is_file() or catalog_path is None:
            abort(404)

        manual_resolutions: dict[int, str] = {}
        entered_values: dict[int, str] = {}
        invalid_rows: list[int] = []
        for field_name, raw_value in request.form.items():
            match = re.fullmatch(r"asin_(\d+)", field_name)
            if not match:
                continue
            source_row = int(match.group(1))
            entered = raw_value.strip().upper()
            entered_values[source_row] = entered
            if not entered:
                continue
            asin = clean_asin(entered)
            if not asin:
                invalid_rows.append(source_row)
            else:
                manual_resolutions[source_row] = asin

        extraction_name = (
            secure_filename(request.form.get("extraction_name", ""))
            or "amazon_extraction.xlsx"
        )
        catalog_name = (
            secure_filename(request.form.get("catalog_name", ""))
            or "category_listings.xlsx"
        )
        all_listings_name = secure_filename(request.form.get("all_listings_name", ""))

        try:
            offline = read_offline_extraction(extraction_path)
            prepared = prepare_comparison(
                records=offline.records,
                requested_asins=offline.requested_asins,
                catalog_path=catalog_path,
                all_listings_path=(
                    all_listings_path if all_listings_path.is_file() else None
                ),
                manual_resolutions=None if invalid_rows else manual_resolutions,
            )
            if invalid_rows:
                return render_template(
                    "resolve_asins.html",
                    run_name=run_name,
                    unresolved=prepared.unresolved_catalog,
                    extraction_name=extraction_name,
                    catalog_name=catalog_name,
                    all_listings_name=all_listings_name,
                    automatic_stats=prepared.resolution_stats,
                    entered_values=entered_values,
                    validation_error=(
                        "Enter a 10-character ASIN containing only letters and numbers "
                        f"for catalog row(s): {', '.join(map(str, invalid_rows))}."
                    ),
                ), 400

            comparison_path = run_dir / "comparison_report.xlsx"
            comparison_stats = write_prepared_comparison(prepared, comparison_path)
            cleanup_pending_inputs(run_dir)
            return render_template(
                "offline_results.html",
                run_name=run_name,
                extraction_name=extraction_name,
                catalog_name=catalog_name,
                requested_count=len(offline.requested_asins),
                record_count=len(offline.records),
                comparison_name=comparison_path.name,
                comparison_stats=comparison_stats,
            )
        except (OfflineWorkbookError, OSError, ValueError) as exc:
            flash(f"Offline comparison failed: {exc}", "error")
            return redirect(url_for("index", tab="offline"))

    @app.get("/download/<run_name>/<kind>")
    def download(run_name: str, kind: str):
        if not RUN_ID_PATTERN.fullmatch(run_name):
            abort(404)
        downloads = {
            "excel": (
                "amazon_extraction.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "comparison": (
                "comparison_report.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "json": ("brightdata_raw.json", "application/json"),
            "metadata": ("run_metadata.json", "application/json"),
        }
        if kind not in downloads:
            abort(404)
        filename, mimetype = downloads[kind]
        path = Path(app.config["PROJECT_DIR"]) / "output" / run_name / filename
        if not path.is_file():
            abort(404)
        return send_file(path, as_attachment=True, download_name=filename, mimetype=mimetype)

    @app.post("/exit")
    def exit_program():
        if request.remote_addr not in {"127.0.0.1", "::1"}:
            abort(403)
        app.config["EXIT_SCHEDULER"]()
        return render_template("closed.html")

    @app.errorhandler(413)
    def file_too_large(_error):
        return render_template(
            "error.html",
            title="File too large",
            message="The combined upload is larger than 25 MB.",
        ), 413

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
