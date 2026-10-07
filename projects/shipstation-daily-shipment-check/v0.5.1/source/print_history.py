
"""Read Windows print records. This module never sends anything to a printer."""

import json
import os
import re
import subprocess
from datetime import date

""" ----------- 1 - READ WINDOWS PRINT HISTORY ----------- """


def read_windows_print_history(ship_date):
    """Return completed print jobs from the computer running this program."""

    if os.name != "nt":
        return {
            "available": False,
            "jobs": [],
            "note": "Windows print history is only available when the program runs on Windows.",
        }

    selected_date = date.fromisoformat(ship_date)

    # Event 307 means that the Windows print spooler completed a print job.
    powershell_code = f"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$logName = 'Microsoft-Windows-PrintService/Operational'
$logInformation = Get-WinEvent -ListLog $logName

if (-not $logInformation.IsEnabled) {{
    @{{
        available = $false
        note = 'Windows PrintService Operational logging is disabled.'
        jobs = @()
    }} | ConvertTo-Json -Compress -Depth 4
    exit
}}

$startDate = [datetime]::new({selected_date.year}, {selected_date.month}, {selected_date.day}, 0, 0, 0)
$endDate = $startDate.AddDays(1)

$events = @(Get-WinEvent -FilterHashtable @{{
    LogName = $logName
    Id = 307
    StartTime = $startDate
    EndTime = $endDate
}} -ErrorAction SilentlyContinue)

$printJobs = @($events | ForEach-Object {{
    $details = $_.Properties

    [PSCustomObject]@{{
        recordId = $_.RecordId
        printedAt = $_.TimeCreated.ToString('o')
        documentName = if ($details.Count -gt 1) {{ [string]$details[1].Value }} else {{ '' }}
        userName = if ($details.Count -gt 2) {{ [string]$details[2].Value }} else {{ '' }}
        computerName = if ($details.Count -gt 3) {{ [string]$details[3].Value }} else {{ $_.MachineName }}
        printerName = if ($details.Count -gt 4) {{ [string]$details[4].Value }} else {{ '' }}
        pages = if ($details.Count -gt 7) {{ $details[7].Value }} else {{ $null }}
    }}
}})

@{{
    available = $true
    note = 'Windows PrintService Event 307 records were checked on this computer.'
    jobs = $printJobs
}} | ConvertTo-Json -Compress -Depth 4
"""

    try:
        completed_process = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", powershell_code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return {
            "available": False,
            "jobs": [],
            "note": "The program could not read Windows print history.",
        }

    if completed_process.returncode != 0 or not completed_process.stdout.strip():
        return {
            "available": False,
            "jobs": [],
            "note": "Windows did not return its print history.",
        }

    try:
        print_history = json.loads(completed_process.stdout.lstrip("\ufeff").strip())
    except json.JSONDecodeError:
        return {
            "available": False,
            "jobs": [],
            "note": "Windows returned print history in an unexpected format.",
        }

    if not isinstance(print_history, dict):
        return {
            "available": False,
            "jobs": [],
            "note": "Windows returned print history in an unexpected format.",
        }

    print_history["jobs"] = print_history.get("jobs") or []
    return print_history


""" ----------- 2 - MATCH PRINT JOBS TO SHIPSTATION ----------- """


def clean_text(value):
    """Remove spaces and punctuation so tracking numbers are easier to compare."""

    return re.sub(r"[^a-zA-Z0-9]", "", str(value or "")).lower()


def get_row_identifiers(order_row):
    """Return the useful numbers that may appear in a print-job name."""

    identifiers = []

    fields = [
        ("Tracking number", order_row.get("tracking")),
        ("Order number", order_row.get("orderNumber")),
        ("Shipment ID", order_row.get("shipmentIds")),
        ("Record ID", order_row.get("recordIds")),
    ]

    for identifier_type, field_value in fields:
        for value in str(field_value or "").split(";"):
            cleaned_value = clean_text(value)

            # Short values create too many accidental matches.
            if len(cleaned_value) >= 6:
                identifiers.append((identifier_type, cleaned_value))

    return identifiers


def add_print_history(order_rows, print_history):
    """Add print information to each row and return only matched print jobs."""

    print_log_available = bool(print_history.get("available"))
    print_jobs = print_history.get("jobs") or []
    matched_print_jobs = {}

    for order_row in order_rows:
        order_row["printStatus"] = "Unknown - print log unavailable"
        order_row["printedAt"] = ""
        order_row["printerName"] = ""
        order_row["printComputer"] = ""
        order_row["printDocument"] = ""
        order_row["printMatch"] = ""
        order_row["printCount"] = 0

        if not print_log_available:
            continue

        matching_jobs = []
        match_type = ""

        for identifier_type, identifier in get_row_identifiers(order_row):
            for print_job in print_jobs:
                document_name = clean_text(print_job.get("documentName"))

                if identifier in document_name:
                    matching_jobs.append(print_job)
                    match_type = identifier_type

            if matching_jobs:
                break

        if not matching_jobs:
            order_row["printStatus"] = "No matching print record"
            continue

        matching_jobs.sort(key=lambda job: job.get("printedAt") or "")
        first_print_job = matching_jobs[0]

        order_row["printStatus"] = "Printed - Windows record found"
        order_row["printedAt"] = first_print_job.get("printedAt") or ""
        order_row["printerName"] = first_print_job.get("printerName") or ""
        order_row["printComputer"] = first_print_job.get("computerName") or ""
        order_row["printDocument"] = first_print_job.get("documentName") or ""
        order_row["printMatch"] = match_type
        order_row["printCount"] = len(matching_jobs)

        for print_job in matching_jobs:
            job_key = (
                str(print_job.get("recordId") or ""),
                str(print_job.get("printedAt") or ""),
                str(print_job.get("documentName") or ""),
            )

            if job_key not in matched_print_jobs:
                matched_print_jobs[job_key] = {
                    **print_job,
                    "matchedOrderNumbers": [],
                    "matchTypes": [],
                }

            saved_job = matched_print_jobs[job_key]
            order_number = order_row.get("orderNumber") or ""

            if order_number and order_number not in saved_job["matchedOrderNumbers"]:
                saved_job["matchedOrderNumbers"].append(order_number)

            if match_type and match_type not in saved_job["matchTypes"]:
                saved_job["matchTypes"].append(match_type)

    final_jobs = []

    for print_job in matched_print_jobs.values():
        print_job["matchedOrderNumbers"] = "; ".join(print_job["matchedOrderNumbers"])
        print_job["matchTypes"] = "; ".join(print_job["matchTypes"])
        final_jobs.append(print_job)

    final_jobs.sort(key=lambda job: job.get("printedAt") or "")
    return final_jobs
