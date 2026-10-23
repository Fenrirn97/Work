const reportForm = document.getElementById("reportForm");
const credentialsFile = document.getElementById("credentialsFile");
const printCsvFile = document.getElementById("printCsvFile");
const shipDateStart = document.getElementById("shipDateStart");
const shipDateEnd = document.getElementById("shipDateEnd");
const checkCarriers = document.getElementById("checkCarriers");
const carrierBrowserArea = document.getElementById("carrierBrowserArea");
const showCarrierBrowser = document.getElementById("showCarrierBrowser");
const reportButton = document.getElementById("reportButton");
const exitButton = document.getElementById("exitButton");
const openShipStationButton = document.getElementById("openShipStationButton");
const shipStationMessage = document.getElementById("shipStationMessage");
const openExtensionFolderButton = document.getElementById("openExtensionFolderButton");
const refreshCaptureButton = document.getElementById("refreshCaptureButton");
const clearCaptureButton = document.getElementById("clearCaptureButton");
const captureStatus = document.getElementById("captureStatus");
const statusMessage = document.getElementById("statusMessage");
const progressBar = document.getElementById("progressBar");
const sectionValue = document.getElementById("sectionValue");
const pageValue = document.getElementById("pageValue");
const timeValue = document.getElementById("timeValue");
const summaryBox = document.getElementById("summaryBox");

function setTodaysDate() {
  const today = new Date();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  shipDateStart.value = `${today.getFullYear()}-${month}-${day}`;
  shipDateEnd.value = shipDateStart.value;
  updateRangeDescription();
}

function updateRangeDescription() {
  const start = shipDateStart.value, end = shipDateEnd.value;
  shipDateEnd.min = start || "2000-01-01";
  shipDateEnd.setCustomValidity(start && end && end < start ? "Through date must be the same as or later than From date." : "");
  const format = iso => {const [year,month,day] = iso.split("-");return `${month}/${day}/${year}`;};
  document.getElementById("rangeDescription").textContent = start && end
    ? `Selected Ship Dates: ${format(start)} through ${format(end)}.` : "Choose both dates.";
}
shipDateStart.addEventListener("change", updateRangeDescription);
shipDateEnd.addEventListener("change", updateRangeDescription);

function formatTime(seconds) {
  if (seconds === undefined || seconds === null || Number.isNaN(Number(seconds))) return "Calculating";
  seconds = Math.max(0, Math.round(Number(seconds)));
  if (seconds < 60) return `${seconds} sec`;
  return `${Math.floor(seconds / 60)} min ${seconds % 60} sec`;
}

function showProgress(update) {
  statusMessage.textContent = update.message || "Working...";
  statusMessage.className = "";
  if (update.section) sectionValue.textContent = update.section;
  if (update.currentPage && update.totalPages) {
    pageValue.textContent = `${update.currentPage} of ${update.totalPages}`;
    progressBar.style.width = `${Math.min(96, (update.currentPage / update.totalPages) * 90)}%`;
  }
  if (update.estimatedSeconds !== undefined) timeValue.textContent = formatTime(update.estimatedSeconds);
}

function showError(message) {
  statusMessage.textContent = message;
  statusMessage.className = "error-message";
  reportButton.disabled = false;
  reportButton.textContent = "Create Compared Excel Report";
}

function downloadExcel(base64File, reportDate) {
  const binaryText = window.atob(base64File);
  const fileBytes = new Uint8Array(binaryText.length);
  for (let i = 0; i < binaryText.length; i += 1) fileBytes[i] = binaryText.charCodeAt(i);
  const excelFile = new Blob([fileBytes], {type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(excelFile);
  link.download = `Shipped_${reportDate}_Checked.xlsx`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function showSummary(report) {
  const items = [
    `Ship Dates: ${report.displayDate || report.shipDate}`,
    `Excel rows: ${report.rowCount ?? 0}`,
    `Shipment groups: ${report.recordCount ?? 0}`,
    `CSV not printed: ${report.notPrintedRowCount ?? 0}`,
    `UI print rows captured: ${report.uiPrintCaptureCount ?? 0}`,
    `UI print rows matched: ${report.uiPrintMatchedRows ?? 0}`,
    `Printed missing time: ${report.uiPrintedMissingTimeCount ?? 0}`,
    `Printed missing tracking: ${report.printedMissingTrackingCount ?? 0}`,
    `Tracking checked: ${report.carrierCheckCount ?? 0}`,
    `Carrier accepted: ${report.carrierAcceptedCount ?? 0}`,
    `No carrier acceptance: ${report.carrierNotAcceptedCount ?? 0}`,
    `Manual carrier checks: ${report.carrierManualCount ?? 0}`
  ];
  summaryBox.replaceChildren();
  for (const value of items) {const span=document.createElement("span");span.textContent=value;summaryBox.append(span);}
  summaryBox.classList.remove("hidden");
}

async function refreshCaptureStatus() {
  try {
    const response = await fetch("/api/print-capture-status", {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not read capture status.");
    if (!data.count) captureStatus.textContent = "No ShipStation print-time rows captured yet.";
    else captureStatus.textContent = `${data.count} unique ShipStation row(s) captured. Latest capture: ${data.latestCapturedAt || "unknown"}.`;
  } catch (error) {
    captureStatus.textContent = error.message || "Could not read capture status.";
  }
}

async function readReportMessages(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let unfinished = "";
  let completed = false;
  while (true) {
    const result = await reader.read();
    unfinished += decoder.decode(result.value || new Uint8Array(), {stream: !result.done});
    const lines = unfinished.split("\n");
    unfinished = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      const message = JSON.parse(line);
      if (message.type === "progress") showProgress(message);
      if (message.type === "error") throw new Error(message.message);
      if (message.type === "complete") {
        completed = true;
        downloadExcel(message.report.fileBase64, message.report.fileRange || message.report.shipDate);
        statusMessage.textContent = "Complete. The combined Excel report has been downloaded.";
        statusMessage.className = "success-message";
        progressBar.style.width = "100%";
        sectionValue.textContent = "Complete";
        pageValue.textContent = "Done";
        timeValue.textContent = "0 sec";
        showSummary(message.report);
      }
    }
    if (result.done) break;
  }
  if (!completed) throw new Error("The connection ended before the report finished. Please run the report again.");
}

checkCarriers.addEventListener("change", () => {
  carrierBrowserArea.classList.toggle("hidden", !checkCarriers.checked);
});

openShipStationButton.addEventListener("click", async () => {
  openShipStationButton.disabled = true;
  shipStationMessage.textContent = "Opening ShipStation in your normal browser...";
  try {
    const response = await fetch("/api/open-shipstation", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not open ShipStation.");
    shipStationMessage.textContent = `${data.message || "ShipStation opened."} Apply the From / Through Ship Dates shown above.`;
  } catch (error) {
    shipStationMessage.textContent = error.message || "Could not open ShipStation.";
  } finally {
    openShipStationButton.disabled = false;
  }
});

openExtensionFolderButton.addEventListener("click", async () => {
  try {
    const response = await fetch("/api/open-extension-folder", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not open extension folder.");
    captureStatus.textContent = "Extension folder opened. In Edge: edge://extensions → Developer mode → Load unpacked → select that folder.";
  } catch (error) {
    captureStatus.textContent = error.message || "Could not open extension folder.";
  }
});

refreshCaptureButton.addEventListener("click", refreshCaptureStatus);

clearCaptureButton.addEventListener("click", async () => {
  try {
    const response = await fetch("/api/clear-print-capture", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not clear capture.");
    await refreshCaptureStatus();
  } catch (error) {
    captureStatus.textContent = error.message || "Could not clear capture.";
  }
});

reportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  updateRangeDescription();
  if (!reportForm.reportValidity()) return;
  if (!credentialsFile.files.length) {
    showError("Choose the ShipStation API TXT file.");
    return;
  }

  reportButton.disabled = true;
  reportButton.textContent = "Creating Report...";
  statusMessage.className = "";
  statusMessage.textContent = "Reading selected files...";
  progressBar.style.width = "2%";
  sectionValue.textContent = "Starting";
  pageValue.textContent = "—";
  timeValue.textContent = "Calculating";
  summaryBox.classList.add("hidden");

  try {
    const credentialsText = await credentialsFile.files[0].text();
    const printCsvText = printCsvFile.files.length ? await printCsvFile.files[0].text() : "";
    const response = await fetch("/api/report", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        credentialsText,
        shipDateStart: shipDateStart.value,
        shipDateEnd: shipDateEnd.value,
        printCsvText,
        checkCarriers: checkCarriers.checked,
        showCarrierBrowser: showCarrierBrowser.checked
      })
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
    reportButton.textContent = "Create Compared Excel Report";
  }
});

exitButton.addEventListener("click", async () => {
  exitButton.disabled = true;
  statusMessage.textContent = "Closing the program...";
  try {
    await fetch("/api/exit", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
  } finally {
    document.body.innerHTML = "<main class='closed-message'><h1>Program closed</h1><p>You may close this browser tab.</p></main>";
  }
});

setTodaysDate();
refreshCaptureStatus();
