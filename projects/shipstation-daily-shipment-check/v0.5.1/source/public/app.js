const reportForm = document.getElementById("reportForm");
const credentialsFile = document.getElementById("credentialsFile");
const shipDate = document.getElementById("shipDate");
const reportButton = document.getElementById("reportButton");
const exitButton = document.getElementById("exitButton");
const openShipStationButton = document.getElementById("openShipStationButton");
const readShipmentsButton = document.getElementById("readShipmentsButton");
const downloadCaptureButton = document.getElementById("downloadCaptureButton");

const statusMessage = document.getElementById("statusMessage");
const captureMessage = document.getElementById("captureMessage");
const progressBar = document.getElementById("progressBar");
const sectionValue = document.getElementById("sectionValue");
const pageValue = document.getElementById("pageValue");
const timeValue = document.getElementById("timeValue");
const captureRows = document.getElementById("captureRows");
const capturePrinted = document.getElementById("capturePrinted");
const captureMissingTime = document.getElementById("captureMissingTime");
const captureMissingTracking = document.getElementById("captureMissingTracking");
const captureUnreadable = document.getElementById("captureUnreadable");
const capturePages = document.getElementById("capturePages");

let captureReady = false;

function setTodaysDate() {
    const today = new Date();
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const day = String(today.getDate()).padStart(2, "0");
    const year = today.getFullYear();
    shipDate.value = `${month}/${day}/${year}`;
}

function formatTime(seconds) {
    if (!Number.isFinite(seconds)) return "—";
    if (seconds < 60) return `${Math.max(0, Math.ceil(seconds))} seconds`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.ceil(seconds % 60);
    return `${minutes} min ${remainingSeconds} sec`;
}

function showProgress(update) {
    statusMessage.textContent = update.message || "Working...";
    statusMessage.className = "";
    if (update.section) sectionValue.textContent = update.section;
    if (update.currentPage && update.totalPages) {
        pageValue.textContent = `${update.currentPage} of ${update.totalPages}`;
        progressBar.style.width = `${Math.min(100, (update.currentPage / update.totalPages) * 100)}%`;
    }
    if (update.estimatedSeconds !== undefined) timeValue.textContent = formatTime(update.estimatedSeconds);
}

function showError(message) {
    statusMessage.textContent = message;
    statusMessage.className = "error-message";
    reportButton.disabled = false;
    reportButton.textContent = "Create Combined Excel Report";
}

function base64ToExcel(base64File, filename) {
    const binaryText = window.atob(base64File);
    const fileBytes = new Uint8Array(binaryText.length);
    for (let index = 0; index < binaryText.length; index += 1) {
        fileBytes[index] = binaryText.charCodeAt(index);
    }
    const excelFile = new Blob(
        [fileBytes],
        {type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    );
    const downloadLink = document.createElement("a");
    downloadLink.href = URL.createObjectURL(excelFile);
    downloadLink.download = filename;
    downloadLink.click();
    URL.revokeObjectURL(downloadLink.href);
}

async function postJson(url, body = {}) {
    const response = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The action could not be completed.");
    return data;
}

openShipStationButton.addEventListener("click", async function () {
    openShipStationButton.disabled = true;
    captureMessage.textContent = "Opening the dedicated ShipStation Edge window...";
    try {
        await postJson("/api/shipstation/open");
        captureMessage.textContent = "ShipStation window opened. Sign in if needed, go to Shipments → Shipments, set your filter, and keep the required columns visible.";
        captureMessage.className = "capture-message success-message";
    } catch (error) {
        captureMessage.textContent = error.message;
        captureMessage.className = "capture-message error-message";
    } finally {
        openShipStationButton.disabled = false;
    }
});

readShipmentsButton.addEventListener("click", async function () {
    readShipmentsButton.disabled = true;
    readShipmentsButton.textContent = "Reading Shipments...";
    captureMessage.textContent = "Reading the current ShipStation Shipments grid. Do not change filters while this runs.";
    captureMessage.className = "capture-message";
    try {
        const result = await postJson("/api/shipstation/read");
        captureReady = true;
        downloadCaptureButton.disabled = false;
        captureRows.textContent = result.rowCount;
        capturePrinted.textContent = result.printedCount;
        captureMissingTime.textContent = result.printedMissingTimeCount;
        captureMissingTracking.textContent = result.printedMissingTrackingCount;
        captureUnreadable.textContent = result.unreadableCount;
        capturePages.textContent = result.pagesRead;
        const problemCount = result.printedMissingTimeCount + result.printedMissingTrackingCount + result.unreadableCount;
        captureMessage.textContent = problemCount
            ? `Capture complete. ${problemCount} row issue(s) need review before relying on the print-status result.`
            : "Capture complete. ShipStation print-status cells were read without the configured completeness warnings.";
        captureMessage.className = problemCount ? "capture-message warning-message" : "capture-message success-message";
    } catch (error) {
        captureReady = false;
        downloadCaptureButton.disabled = true;
        captureMessage.textContent = error.message;
        captureMessage.className = "capture-message error-message";
    } finally {
        readShipmentsButton.disabled = false;
        readShipmentsButton.textContent = "Read Shipments Grid";
    }
});

downloadCaptureButton.addEventListener("click", async function () {
    if (!captureReady) return;
    downloadCaptureButton.disabled = true;
    try {
        const result = await postJson("/api/shipstation/capture-excel");
        const now = new Date();
        const stamp = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")}`;
        base64ToExcel(result.fileBase64, `ShipStation_Print_Status_${stamp}.xlsx`);
    } catch (error) {
        captureMessage.textContent = error.message;
        captureMessage.className = "capture-message error-message";
    } finally {
        downloadCaptureButton.disabled = false;
    }
});

async function readReportMessages(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let unfinishedText = "";
    while (true) {
        const result = await reader.read();
        unfinishedText += decoder.decode(result.value || new Uint8Array(), {stream: !result.done});
        const lines = unfinishedText.split("\n");
        unfinishedText = lines.pop();
        for (const line of lines) {
            if (!line.trim()) continue;
            const message = JSON.parse(line);
            if (message.type === "progress") showProgress(message);
            if (message.type === "error") throw new Error(message.message);
            if (message.type === "complete") {
                base64ToExcel(message.report.fileBase64, `ShipStation_${message.report.shipDate}_Report.xlsx`);
                const printPart = message.report.shipstationPrintCaptured
                    ? ` ${message.report.shipstationPrintMatched} row(s) matched to the ShipStation Label Printed capture.`
                    : " No ShipStation Label Printed capture was loaded.";
                statusMessage.textContent = `Complete. ${message.report.rowCount} Excel row(s) created.${printPart}`;
                statusMessage.className = "success-message";
                progressBar.style.width = "100%";
                sectionValue.textContent = "Complete";
                pageValue.textContent = "Done";
                timeValue.textContent = "0 seconds";
            }
        }
        if (result.done) break;
    }
}

reportForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!credentialsFile.files.length) {
        showError("Choose the ShipStation API TXT file.");
        return;
    }
    reportButton.disabled = true;
    reportButton.textContent = "Creating Report...";
    statusMessage.className = "";
    progressBar.style.width = "2%";
    sectionValue.textContent = "Starting";
    pageValue.textContent = "—";
    timeValue.textContent = "Calculating";
    try {
        const credentialsText = await credentialsFile.files[0].text();
        const response = await fetch("/api/report", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({credentialsText, shipDate: shipDate.value.trim()})
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || "The report could not be created.");
        }
        await readReportMessages(response);
    } catch (error) {
        showError(error.message || "The report could not be created.");
    } finally {
        reportButton.disabled = false;
        reportButton.textContent = "Create Combined Excel Report";
    }
});

exitButton.addEventListener("click", async function () {
    exitButton.disabled = true;
    statusMessage.textContent = "Closing the program and the dedicated ShipStation browser...";
    try {
        await fetch("/api/exit", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: "{}"
        });
    } finally {
        document.body.innerHTML = "<main class='closed-message'><h1>Program closed</h1><p>You may close this browser tab.</p></main>";
    }
});

setTodaysDate();
