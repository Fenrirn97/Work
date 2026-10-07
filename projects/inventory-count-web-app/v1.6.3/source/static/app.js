"use strict";

const appState = {
  data: null,
  editingId: null,
  organizeFile: null,
  comparisonFile: null,
  referenceFile: null,
  sessionReferenceFile: null,
  catalogMatches: [],
  catalogActiveIndex: -1,
  catalogTimer: null,
  catalogRequest: null,
  selectedCatalogItem: null,
  issueOnly: false,
  restoredDraftFor: "",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const numberFormat = new Intl.NumberFormat();

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  return numberFormat.format(Number(value));
}

function formatDifference(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return number > 0 ? `+${numberFormat.format(number)}` : numberFormat.format(number);
}

function formatDate(value, includeTime = true) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const options = { year: "numeric", month: "short", day: "numeric" };
  if (includeTime) Object.assign(options, { hour: "numeric", minute: "2-digit" });
  return new Intl.DateTimeFormat(undefined, options).format(date);
}

function formatEntryTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const time = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(date);
  const day = new Intl.DateTimeFormat("en-US", {
    month: "2-digit",
    day: "2-digit",
    year: "numeric",
  }).format(date);
  return `${time} · ${day}`;
}

function savedLabel(value) {
  if (!value) return "✓ Saved automatically";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "✓ Saved automatically";
  return `✓ Saved automatically · ${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date)}`;
}

function draftKey() {
  return appState.data?.session?.id ? `inventory-entry-draft:${appState.data.session.id}` : "";
}

function saveFormDraft() {
  const key = draftKey();
  if (!key || !appState.data || appState.data.session.status === "FINALIZED") return;
  const payload = {
    panel: document.querySelector(".panel.active")?.id || "countPanel",
    entry: entryPayload(),
    entrySearch: $("#entrySearch")?.value || "",
    issuesOnly: Boolean($("#issuesOnly")?.checked),
    savedAt: new Date().toISOString(),
  };
  localStorage.setItem(key, JSON.stringify(payload));
}

function clearFormDraft() {
  const key = draftKey();
  if (key) localStorage.removeItem(key);
}

function restoreFormDraft() {
  const key = draftKey();
  if (!key || appState.restoredDraftFor === key) return;
  appState.restoredDraftFor = key;
  try {
    const payload = JSON.parse(localStorage.getItem(key) || "null");
    if (!payload?.entry) return;
    const fields = {
      model: "#model", ram: "#ram", storage: "#storage", color: "#color",
      items_per_box: "#itemsPerBox", boxes: "#boxes", loose_items: "#looseItems", area: "#area",
    };
    Object.entries(fields).forEach(([name, selector]) => {
      if (payload.entry[name] !== undefined && payload.entry[name] !== null) $(selector).value = payload.entry[name];
    });
    $("#brokenBox").checked = Boolean(payload.entry.broken_box);
    if (payload.entrySearch) $("#entrySearch").value = payload.entrySearch;
    appState.issueOnly = Boolean(payload.issuesOnly);
    if ($("#issuesOnly")) $("#issuesOnly").checked = appState.issueOnly;
    if (payload.panel && document.getElementById(payload.panel)) showPanel(payload.panel, false);
    calculateAmount();
    renderEntries();
    renderComparisons();
    const hasDraft = [payload.entry.model, payload.entry.color, payload.entry.ram, payload.entry.storage].some(Boolean) ||
      Number(payload.entry.items_per_box) || Number(payload.entry.boxes) || Number(payload.entry.loose_items);
    if (hasDraft) {
      $("#resumeNotice").classList.remove("hidden");
      $("#resumeText").textContent = `Unsaved form values from ${formatDate(payload.savedAt)} were restored.`;
    }
  } catch (_) {
    localStorage.removeItem(key);
  }
}

function focusCountEntry() {
  showPanel("countPanel");
  window.setTimeout(() => $("#model").focus(), 50);
}

function openProblems() {
  appState.issueOnly = true;
  $("#issuesOnly").checked = true;
  showPanel("comparePanel");
  renderComparisons();
}

function setBusy(isBusy, label = "Working…") {
  const overlay = $("#loadingOverlay");
  overlay.classList.toggle("hidden", !isBusy);
  overlay.setAttribute("aria-hidden", String(!isBusy));
  overlay.querySelector("span").textContent = label;
}

function toast(title, message = "", type = "info") {
  const element = document.createElement("div");
  element.className = `toast ${type}`;
  element.innerHTML = `<div><strong>${escapeHtml(title)}</strong>${message ? `<p>${escapeHtml(message)}</p>` : ""}</div>`;
  $("#toastRegion").appendChild(element);
  window.setTimeout(() => element.remove(), 4600);
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const error = new Error(payload?.error || `Request failed with status ${response.status}.`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

async function loadState() {
  appState.data = await request("/api/state");
  renderAll();
}

function renderAll() {
  if (!appState.data) return;
  const { session, summary } = appState.data;
  const workflow = String(session.workflow_status || session.status || "COUNTING");
  $("#sessionSubtitle").textContent = `${session.session_number || "Cycle Count"} · ${session.name} · Attempt ${session.recount_attempt || 1}`;
  const status = $("#sessionStatus");
  status.textContent = workflow.replaceAll("_", " ");
  status.className = `status-pill ${session.status.toLowerCase()}`;
  $("#saveIndicator").textContent = savedLabel(appState.data.last_saved_at);
  $("#rowMetric").textContent = formatNumber(summary.rows);
  $("#unitMetric").textContent = formatNumber(summary.total_amount);
  $("#brokenMetric").textContent = formatNumber(summary.broken_amount);
  $("#matchMetric").textContent = formatNumber(summary.matches);
  $("#issueMetric").textContent = formatNumber(summary.issues);
  $("#comparedMetric").textContent = formatNumber(appState.data.comparisons.length);
  $("#problemsBadge").textContent = formatNumber(summary.issues);
  $("#quickProblemCount").textContent = `${formatNumber(summary.issues)} item${summary.issues === 1 ? "" : "s"} need attention`;
  $("#continueLabel").textContent = `${session.name} · ${formatNumber(summary.rows)} row${summary.rows === 1 ? "" : "s"}`;
  renderCatalogStatus();
  renderRecentItems();
  renderLastWorkbook();
  renderEntries();
  renderComparisons();
  renderSessions();
  renderCycleControls();
  renderMovements();
  applySessionLock();
  restoreFormDraft();
  if (session.status === "DRAFT" && summary.rows > 0 && $("#resumeNotice").classList.contains("hidden")) {
    $("#resumeNotice").classList.remove("hidden");
    $("#resumeText").textContent = `${session.name} has ${formatNumber(summary.rows)} saved count row${summary.rows === 1 ? "" : "s"}.`;
  }
}

function renderRecentItems() {
  const entries = appState.data?.entries || [];
  const seen = new Set();
  const recent = [];
  for (const entry of entries) {
    if (seen.has(entry.match_key)) continue;
    seen.add(entry.match_key);
    recent.push(entry);
    if (recent.length >= 8) break;
  }
  $("#recentItems").classList.toggle("hidden", recent.length === 0);
  $("#recentItemButtons").innerHTML = recent.map((entry) => `
    <button type="button" class="recent-chip" data-recent-id="${escapeHtml(entry.id)}" title="Load ${escapeHtml(entry.item_details)}">
      ${escapeHtml(entry.model)} · ${escapeHtml(entry.color)} · ${formatNumber(entry.amount)}
    </button>`).join("");
}

function renderLastWorkbook() {
  const saved = appState.data?.last_workbook;
  $("#lastWorkbookCard").classList.toggle("hidden", !saved);
  $("#reuseLastReferenceButton").classList.toggle("hidden", !saved);
  if (!saved) return;
  $("#lastWorkbookName").textContent = saved.source_name;
  const validation = saved.validation || {};
  $("#lastWorkbookDetails").textContent = `${formatNumber(validation.extracted_rows || 0)} rows · ${formatNumber(validation.unique_variants || 0)} variants · saved ${formatDate(saved.saved_at)}`;
  $("#reuseLastReferenceButton").textContent = `Use Last Validated Workbook · ${saved.source_name}`;
}

function renderCatalogStatus() {
  const catalog = appState.data?.catalog || {};
  const count = Number(catalog.variant_count || 0);
  const status = $("#catalogStatus");
  status.classList.toggle("ready", count > 0);
  status.textContent = count > 0
    ? `${formatNumber(count)} autocomplete variant${count === 1 ? "" : "s"} loaded from ${catalog.source_name || "the organized workbook"}. Type a model and select the correct RAM, Storage, and Color.`
    : "No autocomplete catalog loaded. Use Organize Excel to load one.";
}

function hideModelSuggestions() {
  const menu = $("#modelSuggestions");
  menu.classList.add("hidden");
  menu.innerHTML = "";
  $("#model").setAttribute("aria-expanded", "false");
  appState.catalogMatches = [];
  appState.catalogActiveIndex = -1;
}

function variantDetails(item) {
  const memory = item.ram && item.storage    ? `${item.ram} RAM · ${item.storage} Storage`
    : "Non-memory item";
  const sources = Number(item.source_rows || 1);
  const inventory = item.reference_quantity === null || item.reference_quantity === undefined
    ? "Expected Units: —"
    : `Expected Units: ${formatNumber(item.reference_quantity)}`;
  return `${item.color} · ${memory} · ${inventory}${sources > 1 ? ` · ${sources} source rows` : ""}`;
}

function renderSelectedInventoryQuantity(item = null) {
  appState.selectedCatalogItem = item;
  const panel = $("#selectedInventoryQuantity");
  if (!panel) return;
  if (!item) {
    panel.classList.add("hidden");
    $("#inventoryQuantityValue").textContent = "—";
    $("#currentCountValue").textContent = "0";
    $("#liveDifferenceValue").textContent = "—";
    $("#liveDifferenceValue").className = "";
    $("#inventoryQuantityDetails").textContent = "Select a product from autocomplete to see the expected unit count.";
    return;
  }
  const quantity = item.reference_quantity === null || item.reference_quantity === undefined
    ? "—"
    : formatNumber(item.reference_quantity);
  $("#inventoryQuantityValue").textContent = quantity;
  $("#inventoryQuantityDetails").textContent = `${item.model} · ${item.color}${item.ram && item.storage ? ` · ${item.ram} RAM · ${item.storage} Storage` : ""}`;
  panel.classList.remove("hidden");
  updateExpectedUnitSummary();
}

function updateExpectedUnitSummary() {
  const current = $("#currentCountValue");
  const difference = $("#liveDifferenceValue");
  if (!current || !difference) return;

  const perBox = Math.max(0, Number.parseInt($("#itemsPerBox").value || "0", 10) || 0);
  const boxes = Math.max(0, Number.parseInt($("#boxes").value || "0", 10) || 0);
  const loose = Math.max(0, Number.parseInt($("#looseItems").value || "0", 10) || 0);
  const counted = (perBox * boxes) + loose;
  current.textContent = formatNumber(counted);

  const expected = appState.selectedCatalogItem?.reference_quantity;
  if (expected === null || expected === undefined || expected === "") {
    difference.textContent = "—";
    difference.className = "";
    return;
  }

  const delta = counted - Number(expected);
  difference.textContent = formatDifference(delta);
  difference.className = delta === 0 ? "difference-match" : delta < 0 ? "difference-under" : "difference-over";
}

function clearSelectedInventoryQuantity() {
  renderSelectedInventoryQuantity(null);
}

function renderModelSuggestions(items) {
  const menu = $("#modelSuggestions");
  appState.catalogMatches = items;
  appState.catalogActiveIndex = -1;
  if (!items.length) {
    menu.innerHTML = '<div class="autocomplete-empty">No catalog matches. You can continue entering the product manually.</div>';
  } else {
    menu.innerHTML = items.map((item, index) => `
      <button class="autocomplete-option" type="button" role="option" data-catalog-index="${index}" aria-selected="false">
        <strong>${escapeHtml(item.model)}</strong>
        <span>${escapeHtml(variantDetails(item))}</span>
        ${Number(item.source_rows || 1) > 1 && item.source_locations ? `<span class="autocomplete-source">Source: ${escapeHtml(item.source_locations)}</span>` : ""}
      </button>`).join("");
  }
  menu.classList.remove("hidden");
  $("#model").setAttribute("aria-expanded", "true");
}

function setActiveCatalogOption(index) {
  if (!appState.catalogMatches.length) return;
  const length = appState.catalogMatches.length;
  appState.catalogActiveIndex = (index + length) % length;
  $$("#modelSuggestions .autocomplete-option").forEach((option, optionIndex) => {
    const active = optionIndex === appState.catalogActiveIndex;
    option.dataset.active = String(active);
    option.setAttribute("aria-selected", String(active));
    if (active) option.scrollIntoView({ block: "nearest" });
  });
}

function selectCatalogVariant(index) {
  const item = appState.catalogMatches[index];
  if (!item) return;
  const nonMemory = !item.ram && !item.storage;
  $("#model").value = item.model;
  $("#ram").value = nonMemory ? "0" : item.ram;
  $("#storage").value = nonMemory ? "0" : item.storage;
  $("#color").value = item.color;
  renderSelectedInventoryQuantity(item);
  hideModelSuggestions();
  saveFormDraft();
  $("#itemsPerBox").focus();
}

function loadRecentItem(entryId) {
  const entry = appState.data?.entries?.find((row) => row.id === entryId);
  if (!entry || appState.data.session.status === "FINALIZED") return;
  appState.editingId = null;
  clearSelectedInventoryQuantity();
  $("#model").value = entry.model;
  $("#ram").value = entry.ram;
  $("#storage").value = entry.storage;
  $("#color").value = entry.color;
  $("#itemsPerBox").value = "0";
  $("#boxes").value = "0";
  $("#looseItems").value = "0";
  $("#area").value = entry.area || appState.data.session.location || "";
  $("#brokenBox").checked = false;
  $("#saveEntryButton").textContent = "Add Count";
  $("#cancelEditButton").classList.add("hidden");
  $("#editBadge").classList.add("hidden");
  calculateAmount();
  saveFormDraft();
  showPanel("countPanel");
  $("#itemsPerBox").focus();
}

async function loadModelSuggestions(query) {
  if (appState.catalogRequest) appState.catalogRequest.abort();
  appState.catalogRequest = new AbortController();
  try {
    const result = await request(`/api/catalog?q=${encodeURIComponent(query)}`, {
      signal: appState.catalogRequest.signal,
    });
    if ($("#model").value.trim() !== query) return;
    renderModelSuggestions(result.items || []);
  } catch (error) {
    if (error.name !== "AbortError") hideModelSuggestions();
  }
}

function queueModelSuggestions() {
  window.clearTimeout(appState.catalogTimer);
  const query = $("#model").value.trim();
  if (query.length < 2 || Number(appState.data?.catalog?.variant_count || 0) === 0) {
    hideModelSuggestions();
    return;
  }
  appState.catalogTimer = window.setTimeout(() => loadModelSuggestions(query), 140);
}

function applySessionLock() {
  const locked = appState.data.session.status === "FINALIZED";
  const counting = appState.data.session.workflow_status === "COUNTING";
  $$("#entryForm input, #entryForm button").forEach((control) => {
    control.disabled = locked || !counting;
  });
  $("#finalizeButton").disabled = locked || appState.data.entries.length === 0 ||
    (Boolean(appState.data.reference) && appState.data.session.workflow_status !== "APPROVED");
  $("#freezeReferenceButton").disabled = locked || appState.data.entries.length > 0;
  if (locked && appState.editingId) resetEntryForm(false);
}

function showPanel(panelId, persist = true) {
  $$(".panel").forEach((panel) => panel.classList.toggle("active", panel.id === panelId));
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.panel === panelId));
  if (persist) saveFormDraft();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function calculateAmount() {
  const perBox = Math.max(0, Number.parseInt($("#itemsPerBox").value || "0", 10) || 0);
  const boxes = Math.max(0, Number.parseInt($("#boxes").value || "0", 10) || 0);
  const loose = Math.max(0, Number.parseInt($("#looseItems").value || "0", 10) || 0);
  const amount = (perBox * boxes) + loose;
  $("#calculatedAmount").textContent = numberFormat.format(amount);
  $("#calculationFormula").textContent = `(${numberFormat.format(perBox)} × ${numberFormat.format(boxes)}) + ${numberFormat.format(loose)}`;
  updateExpectedUnitSummary();
}

function entryPayload() {
  return {
    model: $("#model").value,
    ram: $("#ram").value,
    storage: $("#storage").value,
    color: $("#color").value,
    items_per_box: $("#itemsPerBox").value,
    boxes: $("#boxes").value,
    loose_items: $("#looseItems").value,
    area: $("#area").value,
    broken_box: $("#brokenBox").checked,
  };
}

function resetEntryForm(keepIdentity = false, removeDraft = true) {
  hideModelSuggestions();
  appState.editingId = null;
  if (!keepIdentity) {
    clearSelectedInventoryQuantity();
    $("#model").value = "";
    $("#ram").value = "";
    $("#storage").value = "";
    $("#color").value = "";
  }
  $("#itemsPerBox").value = "0";
  $("#boxes").value = "0";
  $("#looseItems").value = "0";
  $("#area").value = appState.data?.session?.location || "";
  $("#brokenBox").checked = false;
  $("#saveEntryButton").textContent = "Add Count";
  $("#cancelEditButton").classList.add("hidden");
  $("#editBadge").classList.add("hidden");
  calculateAmount();
  if (removeDraft) clearFormDraft();
}

function beginEdit(entryId) {
  const entry = appState.data.entries.find((row) => row.id === entryId);
  if (!entry || appState.data.session.status === "FINALIZED") return;
  appState.editingId = entryId;
  hideModelSuggestions();
  clearSelectedInventoryQuantity();
  $("#model").value = entry.model;
  $("#ram").value = entry.ram;
  $("#storage").value = entry.storage;
  $("#color").value = entry.color;
  $("#itemsPerBox").value = entry.items_per_box;
  $("#boxes").value = entry.boxes;
  $("#looseItems").value = entry.loose_items;
  $("#area").value = entry.area;
  $("#brokenBox").checked = Boolean(entry.broken_box);
  $("#saveEntryButton").textContent = "Save Changes";
  $("#cancelEditButton").classList.remove("hidden");
  $("#editBadge").classList.remove("hidden");
  calculateAmount();
  saveFormDraft();
  showPanel("countPanel");
  $("#model").focus();
}

function renderEntries() {
  const rows = $("#entryRows");
  const locked = appState.data.session.status === "FINALIZED";
  const query = $("#entrySearch").value.trim().toLowerCase();
  const issueKeys = new Set(
    (appState.data.comparisons || [])
      .filter((row) => row.result !== "MATCH" && row.match_key)
      .map((row) => row.match_key)
  );
  const entries = appState.data.entries.filter((entry) =>
    [entry.item_details, entry.color, entry.area].some((value) => String(value).toLowerCase().includes(query))
  );
  rows.innerHTML = entries.map((entry) => {
    const needsReview = issueKeys.has(entry.match_key);
    const statusClass = locked ? "locked" : needsReview ? "review" : "counted";
    const statusText = locked ? "Locked" : needsReview ? "Needs Review" : "Counted";
    const duplicate = Number(entry.identity_count || 1) > 1
      ? `<span class="duplicate-marker" title="This product identity has ${formatNumber(entry.identity_count)} count rows">${formatNumber(entry.identity_count)} count rows</span>`
      : "";
    return `
    <tr>
      <td><span class="row-status ${statusClass}">${locked ? "🔒" : needsReview ? "⚠" : "✓"} ${statusText}</span></td>
      <td><strong>${escapeHtml(entry.item_details)}</strong>${entry.broken_box ? '<span class="broken-marker">Broken Box</span>' : ""}${duplicate}</td>
      <td>${escapeHtml(entry.color)}</td>
      <td class="numeric"><strong>${formatNumber(entry.amount)}</strong></td>
      <td>${escapeHtml(entry.area)}</td>
      <td class="calculation-cell">${escapeHtml(entry.calculation)}</td>
      <td class="date-cell" title="Original entry date and time">${escapeHtml(formatEntryTimestamp(entry.counted_at))}</td>
      <td class="actions-column">${locked ? '<span class="date-cell">Locked</span>' : `<div class="row-actions">
        <button class="row-action-text" type="button" data-action="edit" data-id="${escapeHtml(entry.id)}" aria-label="Edit ${escapeHtml(entry.item_details)}">Edit</button>
        <button class="row-action-text danger" type="button" data-action="delete" data-id="${escapeHtml(entry.id)}" aria-label="Remove ${escapeHtml(entry.item_details)}">Remove</button>
      </div>`}</td>
    </tr>`;
  }).join("");
  const empty = $("#entryEmpty");
  empty.classList.toggle("hidden", entries.length > 0);
  rows.parentElement.classList.toggle("hidden", entries.length === 0);
}

async function saveEntry(allowDuplicate = false) {
  const payload = { ...entryPayload(), allow_duplicate: allowDuplicate };
  const editing = Boolean(appState.editingId);
  const url = editing ? `/api/entries/${encodeURIComponent(appState.editingId)}` : "/api/entries";
  try {
    setBusy(true, editing ? "Saving changes…" : "Adding count…");
    await request(url, {
      method: editing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    resetEntryForm(!editing);
    await loadState();
    clearFormDraft();
    focusCountEntry();
    $("#model").focus();
    toast(editing ? "Entry updated" : "Count added", "Your database was saved automatically.", "success");
  } catch (error) {
    if (error.status === 409 && error.payload?.code === "DUPLICATE" && !allowDuplicate) {
      setBusy(false);
      if (window.confirm(`${error.message}\n\nAdd this as another count row?`)) {
        return saveEntry(true);
      }
      return;
    }
    toast("Could not save the entry", error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function deleteEntry(entryId) {
  const entry = appState.data.entries.find((row) => row.id === entryId);
  if (!entry || !window.confirm(`Remove this count row?\n\n${entry.item_details} | ${entry.color} | ${formatNumber(entry.amount)}`)) return;
  try {
    setBusy(true, "Removing count…");
    await request(`/api/entries/${encodeURIComponent(entryId)}`, { method: "DELETE" });
    if (appState.editingId === entryId) resetEntryForm(false);
    await loadState();
    toast("Count removed", "The session database has been updated.", "success");
  } catch (error) {
    toast("Could not remove the entry", error.message, "error");
  } finally {
    setBusy(false);
  }
}

function resultClass(result) {
  if (result === "MATCH") return "match";
  if (["MISSING ITEMS", "EXTRA ITEMS", "AMOUNT CHANGED"].includes(result)) return "warning";
  if (["ATTRIBUTE CONFLICT", "INVALID REFERENCE"].includes(result)) return "conflict";
  if (result === "NEW ITEM") return "info";
  return "error";
}

function renderComparisons() {
  const allResults = appState.data.comparisons || [];
  const results = appState.issueOnly ? allResults.filter((row) => row.result !== "MATCH") : allResults;
  $("#comparisonRows").innerHTML = results.map((row) => `
    <tr>
      <td><span class="result-badge ${resultClass(row.result)}">${escapeHtml(row.result)}</span></td>
      <td><strong>${escapeHtml(row.item)}</strong></td>
      <td>${escapeHtml(row.color)}</td>
      <td class="numeric">${formatNumber(row.counted)}</td>
      <td class="numeric">${formatNumber(row.baseline)}</td>
      <td class="numeric">${formatDifference(row.difference)}</td>
      <td class="numeric">${formatNumber(row.broken_amount)}</td>
      <td class="explanation-cell">${escapeHtml(row.explanation)}${row.review_status ? `<br><strong>${escapeHtml(row.review_status)}</strong>` : ""}${row.movement_warning ? `<br><span class="movement-warning">Movement warning: ${escapeHtml(row.movement_warning)}</span>` : ""}</td>
    </tr>`).join("");
  const empty = $("#comparisonEmpty");
  empty.classList.toggle("hidden", results.length > 0);
  $("#comparisonRows").parentElement.classList.toggle("hidden", results.length === 0);
  if (!results.length && allResults.length && appState.issueOnly) {
    empty.querySelector("h3").textContent = "No problems found";
    empty.querySelector("p").textContent = "Every compared inventory identity currently matches.";
  } else {
    empty.querySelector("h3").textContent = "No comparison results";
    empty.querySelector("p").textContent = "Select an Excel workbook and run a comparison.";
  }
  $("#copyIssuesButton").disabled = !allResults.some((row) => row.result !== "MATCH");
}

async function runComparison() {
  const mode = $("#comparisonMode").value;
  if (!appState.comparisonFile) {
    toast("Select an Excel workbook", "Choose the comparison source before continuing.", "error");
    return;
  }
  if (mode === "old-reference" && !appState.referenceFile) {
    toast("Select a reference workbook", "Old Count vs Reference Sheet requires both workbooks.", "error");
    return;
  }
  if (mode !== "old-reference" && !appState.data.entries.length) {
    toast("No current inventory", "Add at least one count before comparing.", "error");
    return;
  }
  try {
    setBusy(true, "Reading and comparing workbook…");
    let body = appState.comparisonFile;
    let contentType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    if (mode === "old-reference") {
      const [oldBuffer, referenceBuffer] = await Promise.all([
        appState.comparisonFile.arrayBuffer(),
        appState.referenceFile.arrayBuffer(),
      ]);
      const payload = new Uint8Array(4 + oldBuffer.byteLength + referenceBuffer.byteLength);
      new DataView(payload.buffer).setUint32(0, oldBuffer.byteLength, false);
      payload.set(new Uint8Array(oldBuffer), 4);
      payload.set(new Uint8Array(referenceBuffer), 4 + oldBuffer.byteLength);
      body = payload;
      contentType = "application/vnd.inventory.old-reference";
    }
    const result = await request(`/api/compare/${mode}`, {
      method: "POST",
      headers: { "Content-Type": contentType },
      body,
    });
    await loadState();
    toast("Comparison complete", `${formatNumber(result.result_count)} product identities were reviewed.`, "success");
  } catch (error) {
    toast("Comparison failed", error.message, "error");
  } finally {
    setBusy(false);
  }
}

function copyIssues() {
  const issues = appState.data.comparisons.filter((row) => row.result !== "MATCH");
  if (!issues.length) return;
  const text = issues.map((row) =>
    `${row.result} | ${row.item} | ${row.color} | Counted: ${row.counted} | Difference: ${row.difference ?? "n/a"} | ${row.explanation}`
  ).join("\n");
  navigator.clipboard.writeText(text)
    .then(() => toast("Issue list copied", `${issues.length} issue${issues.length === 1 ? "" : "s"} copied to the clipboard.`, "success"))
    .catch(() => toast("Copy failed", "Your browser did not allow clipboard access.", "error"));
}

async function organizeWorkbook() {
  const sourceFile = appState.organizeFile;
  if (!sourceFile) {
    toast("Select an Excel workbook", "Choose the original workbook before creating the organized copy.", "error");
    return;
  }
  try {
    setBusy(true, "Validating workbook…");
    const preview = await request("/api/organize/preview", {
      method: "POST",
      headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
      body: sourceFile,
    });
    $("#organizePreview").classList.remove("hidden");
    const skipped = preview.skipped_examples || [];
    const duplicates = preview.duplicate_groups || [];
    const dates = preview.date_breakdown || [];
    const skippedDetails = skipped.slice(0, 6).map((item) =>
      `<li><strong>${escapeHtml(item.sheet)}!${formatNumber(item.row)}</strong> — ${escapeHtml(item.reason)}${item.model ? ` · ${escapeHtml(item.model)}` : ""}</li>`
    ).join("");
    const duplicateDetails = duplicates.slice(0, 5).map((item) =>
      `<li><strong>${escapeHtml(item.model)} · ${escapeHtml(item.color)}</strong> — ${formatNumber(item.row_count)} source rows${item.source_rows?.length ? ` (${escapeHtml(item.source_rows.join(", "))})` : ""}</li>`
    ).join("");
    const dateDetails = dates.slice(0, 8).map((item) => `${escapeHtml(item.date)}: ${formatNumber(item.rows)}`).join(" · ");
    $("#organizePreview").innerHTML = `
      <div class="import-check">
        <strong>Import Check</strong>
        <div class="import-check-grid">
          <div class="import-check-stat"><span>Rows found</span><strong>${formatNumber(preview.candidate_rows)}</strong></div>
          <div class="import-check-stat"><span>Rows imported</span><strong>${formatNumber(preview.extracted_rows)}</strong></div>
          <div class="import-check-stat"><span>Unique variants</span><strong>${formatNumber(preview.unique_variants)}</strong></div>
          <div class="import-check-stat"><span>Skipped</span><strong>${formatNumber(preview.skipped_rows)}</strong></div>
          <div class="import-check-stat"><span>Duplicate source rows</span><strong>${formatNumber(preview.duplicate_rows)}</strong></div>
          <div class="import-check-stat"><span>Inventory sections</span><strong>${formatNumber(preview.section_count)}</strong></div>
        </div>
        <div class="${preview.skipped_rows ? "import-check-warning" : "import-check-ok"}">
          ${preview.skipped_rows ? `⚠ ${formatNumber(preview.skipped_rows)} source row${preview.skipped_rows === 1 ? "" : "s"} cannot be imported. Their locations and reasons are shown below.` : "✓ 0 rows skipped. Every detected inventory row was accounted for."}
        </div>
        ${skippedDetails ? `<details><summary>Rows needing attention</summary><ul class="import-detail-list">${skippedDetails}</ul></details>` : ""}
        ${duplicateDetails ? `<details><summary>Duplicate product identities (${formatNumber(preview.duplicate_group_count)})</summary><ul class="import-detail-list">${duplicateDetails}</ul></details>` : ""}
        ${dateDetails ? `<small><strong>Date Counted:</strong> ${dateDetails}${dates.length > 8 ? " · …" : ""}</small>` : '<small>No count date detected in imported rows.</small>'}
      </div>`;
    setBusy(false);
    if (!window.confirm(`Workbook validation complete.\n\nSource rows found: ${preview.candidate_rows}\nRows that will be imported: ${preview.extracted_rows}\nRows skipped: ${preview.skipped_rows}\nUnique variants: ${preview.unique_variants}\nDuplicate source rows: ${preview.duplicate_rows}\n\nCreate the organized copy and load the autocomplete catalog?`)) return;
    setBusy(true, "Creating the organized copy…");
    const response = await fetch(`/api/organize?name=${encodeURIComponent(sourceFile.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
      body: sourceFile,
    });
    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json") ? await response.json() : null;
      throw new Error(payload?.error || `Request failed with status ${response.status}.`);
    }
    const workbook = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const matchedName = disposition.match(/filename="?([^";]+)"?/i)?.[1];
    const fallbackStem = sourceFile.name.replace(/\.(?:xlsx|xlsm)$/i, "") || "Inventory";
    const downloadName = matchedName || `${fallbackStem}_Organized.xlsx`;
    const downloadUrl = URL.createObjectURL(workbook);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = downloadName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    const rowCount = Number(response.headers.get("x-organized-rows") || 0);
    const variantCount = Number(response.headers.get("x-catalog-variants") || 0);
    await loadState();
    toast(
      "Organized copy and autocomplete ready",
      `${formatNumber(rowCount)} row${rowCount === 1 ? "" : "s"} extracted and ${formatNumber(variantCount)} unique product variant${variantCount === 1 ? "" : "s"} loaded. The original workbook was not changed.`,
      "success",
    );
  } catch (error) {
    toast("Could not organize the workbook", error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function reuseLastReference() {
  const saved = appState.data?.last_workbook;
  if (!saved) return;
  try {
    setBusy(true, "Loading last validated workbook…");
    const sessionId = appState.data.session.id;
    await request(`/api/sessions/${encodeURIComponent(sessionId)}/reference/reuse`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    });
    await loadState();
    showPanel("comparePanel");
    toast("Reference ready", `${saved.source_name} was reused without browsing for the file again.`, "success");
  } catch (error) {
    toast("Could not reuse the workbook", error.message, "error");
  } finally {
    setBusy(false);
  }
}

function renderSessions() {
  const { session, summary, sessions } = appState.data;
  $("#activeSessionName").textContent = session.name;
  $("#activeSessionStatus").textContent = String(session.workflow_status || session.status).replaceAll("_", " ");
  $("#activeSessionCreated").textContent = formatDate(session.created_at);
  $("#activeSessionEntries").textContent = formatNumber(summary.rows);
  $("#activeSessionUnits").textContent = formatNumber(summary.total_amount);
  $("#activeSessionReference").textContent = session.reference_name || "Not loaded";
  $("#activeSessionAttempt").textContent = formatNumber(session.recount_attempt || 1);
  $("#sessionRows").innerHTML = sessions.map((row) => `
    <tr class="${row.active ? "active-row" : ""}">
      <td><strong>${escapeHtml(row.name)}</strong>${row.active ? '<span class="broken-marker">Active</span>' : ""}</td>
      <td><span class="session-status ${row.status.toLowerCase()}">${escapeHtml(String(row.workflow_status || row.status).replaceAll("_", " "))}</span></td>
      <td class="date-cell">${escapeHtml(formatDate(row.created_at))}</td>
      <td class="numeric">${formatNumber(row.entry_count)}</td>
      <td class="numeric">${formatNumber(row.total_amount)}</td>
      <td class="numeric">${formatNumber(row.broken_amount)}</td>
      <td class="actions-column">${row.active ? '<span class="date-cell">Currently open</span>' : `<button class="button secondary small" data-action="activate-session" data-id="${escapeHtml(row.id)}" type="button">Open</button>`}</td>
    </tr>`).join("");
}

async function createSession(payload) {
  try {
    saveFormDraft();
    setBusy(true, "Creating session…");
    await request("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    resetEntryForm(false, false);
    appState.restoredDraftFor = "";
    appState.comparisonFile = null;
    appState.referenceFile = null;
    appState.sessionReferenceFile = null;
    $("#comparisonFile").value = "";
    $("#referenceFile").value = "";
    $("#selectedFile").textContent = "No workbook selected";
    $("#selectedReferenceFile").textContent = "No reference workbook selected";
    await loadState();
    showPanel("countPanel");
    toast("New session created", "Inventory entries will be saved automatically.", "success");
  } catch (error) {
    toast("Could not create the session", error.message, "error");
  } finally {
    setBusy(false);
  }
}

function renderCycleControls() {
  const { session, reference } = appState.data;
  const workflow = String(session.workflow_status || "COUNTING");
  $("#workflowStatus").textContent = workflow.replaceAll("_", " ");
  $("#referenceName").textContent = reference?.source_name || "No frozen reference";
  $("#referenceDetails").textContent = reference
    ? `${formatNumber(reference.row_count)} reference rows · frozen ${formatDate(reference.created_at)}`
    : "Load a reference from Session History before submitting.";
  $("#referenceHash").textContent = reference ? `SHA256 ${reference.source_hash}` : "";
  const quantity = Number(session.quantity_tolerance || 0);
  const percentage = Number(session.percentage_tolerance || 0);
  $("#toleranceText").textContent = quantity || percentage
    ? `Supervisor review within ±${quantity} units or ${percentage}%`
    : "Exact matches required; differences require recount or approval";
  $("#submitCountButton").disabled = session.status === "FINALIZED" || workflow !== "COUNTING" || !reference || !appState.data.entries.length;
  $("#reviewControls").classList.toggle("hidden", !["PENDING_REVIEW", "RECOUNT_REQUIRED"].includes(workflow));
  $("#referenceCountNote").classList.toggle("hidden", workflow !== "COUNTING");
  $("#countContext").textContent = [session.count_type, session.warehouse, session.location, session.operator_name]
    .filter(Boolean).join(" · ") || "Set warehouse, location, and operator when creating the session.";
  if (!$("#area").value && session.location) $("#area").value = session.location;
  if (!$("#movementOperator").value && session.operator_name) $("#movementOperator").value = session.operator_name;
}

async function freezeReference() {
  const file = appState.sessionReferenceFile;
  const session = appState.data.session;
  if (!file) {
    toast("Select a reference workbook", "Choose the reference before freezing it.", "error");
    return;
  }
  if (appState.data.entries.length) {
    toast("Reference must be loaded first", "Start a new session to use a different frozen reference.", "error");
    return;
  }
  try {
    setBusy(true, "Validating and freezing reference…");
    const response = await fetch(`/api/sessions/${encodeURIComponent(session.id)}/reference?name=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
      body: file,
    });
    if (!response.ok) {
      const payload = (response.headers.get("content-type") || "").includes("application/json") ? await response.json() : null;
      throw new Error(payload?.error || `Request failed with status ${response.status}.`);
    }
    const workbook = await response.blob();
    const name = (response.headers.get("content-disposition") || "").match(/filename="?([^";]+)"?/i)?.[1] || "Reference_Organized.xlsx";
    const url = URL.createObjectURL(workbook);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    await loadState();
    toast("Reference frozen", "The organized copy was downloaded. The selected original was not changed.", "success");
  } catch (error) {
    toast("Could not freeze the reference", error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function submitCycleCount() {
  if (!window.confirm("Submit this count for final review?\n\nCounts cannot be edited again unless a supervisor starts a recount.")) return;
  try {
    setBusy(true, "Comparing against the frozen reference…");
    const result = await request(`/api/sessions/${encodeURIComponent(appState.data.session.id)}/submit`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    });
    await loadState();
    showPanel("comparePanel");
    toast("Count submitted", `${formatNumber(result.result_count)} identities reviewed · ${result.workflow_status.replaceAll("_", " ")}.`, "success");
  } catch (error) {
    toast("Could not submit the count", error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function reviewCycle(action) {
  const reviewer = $("#reviewerName").value.trim();
  const reason = $("#reviewReason").value.trim();
  if (!reviewer || !reason) {
    toast("Review details required", "Enter the reviewer name and decision reason.", "error");
    return;
  }
  if (!window.confirm(action === "APPROVE" ? "Approve this submitted count?" : "Start a new recount attempt? The prior attempt remains in history.")) return;
  try {
    setBusy(true, action === "APPROVE" ? "Recording approval…" : "Opening recount…");
    await request(`/api/sessions/${encodeURIComponent(appState.data.session.id)}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, reviewer, reason }),
    });
    resetEntryForm(false);
    await loadState();
    if (action === "RECOUNT") showPanel("countPanel");
    toast(action === "APPROVE" ? "Count approved" : "Recount started", "The decision was added to the audit history.", "success");
  } catch (error) {
    toast("Could not save the decision", error.message, "error");
  } finally {
    setBusy(false);
  }
}

function renderMovements() {
  const movements = appState.data.movements || [];
  $("#movementRows").innerHTML = movements.map((row) => `
    <tr><td class="date-cell">${escapeHtml(formatDate(row.occurred_at))}</td><td>${escapeHtml(row.movement_type.replaceAll("_", " "))}</td>
    <td><strong>${escapeHtml(row.model)}</strong><br><span class="date-cell">${escapeHtml(row.ram)} · ${escapeHtml(row.storage)}</span></td>
    <td>${escapeHtml(row.color)}</td><td class="numeric">${formatNumber(row.quantity)}</td><td>${escapeHtml(row.from_location || "—")}</td>
    <td>${escapeHtml(row.to_location || "—")}</td><td>${escapeHtml(row.operator_name)}</td><td>${escapeHtml(row.note || "")}</td></tr>`).join("");
  $("#movementEmpty").classList.toggle("hidden", movements.length > 0);
  $("#movementRows").parentElement.classList.toggle("hidden", movements.length === 0);
}

async function saveMovement() {
  const payload = {
    movement_type: $("#movementType").value, model: $("#movementModel").value,
    ram: $("#movementRam").value, storage: $("#movementStorage").value,
    color: $("#movementColor").value, quantity: $("#movementQuantity").value,
    from_location: $("#movementFrom").value, to_location: $("#movementTo").value,
    operator_name: $("#movementOperator").value, note: $("#movementNote").value,
  };
  try {
    setBusy(true, "Saving movement…");
    await request("/api/movements", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    $("#movementForm").reset();
    $("#movementQuantity").value = "1";
    await loadState();
    toast("Movement saved", "It will be checked as a warning during cycle-count submission.", "success");
  } catch (error) {
    toast("Could not save the movement", error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function activateSession(sessionId) {
  try {
    saveFormDraft();
    setBusy(true, "Opening session…");
    await request(`/api/sessions/${encodeURIComponent(sessionId)}/activate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    resetEntryForm(false, false);
    appState.restoredDraftFor = "";
    await loadState();
    showPanel("countPanel");
    toast("Session opened", appState.data.session.name, "success");
  } catch (error) {
    toast("Could not open the session", error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function finalizeCurrentSession() {
  const session = appState.data.session;
  if (!window.confirm(`Finalize and lock “${session.name}”?\n\nYou will still be able to export it, but its inventory rows can no longer be changed.`)) return;
  try {
    setBusy(true, "Finalizing session…");
    await request(`/api/sessions/${encodeURIComponent(session.id)}/finalize`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await loadState();
    toast("Session finalized", "The inventory count is now locked against accidental changes.", "success");
  } catch (error) {
    toast("Could not finalize the session", error.message, "error");
  } finally {
    setBusy(false);
  }
}

function exportWorkbook() {
  if (!appState.data.entries.length) {
    toast("Nothing to export", "Add at least one inventory count first.", "error");
    return;
  }
  window.location.assign("/api/export");
  toast("Preparing Excel workbook", "The download should begin automatically.", "info");
}

function updateComparisonMode() {
  const mode = $("#comparisonMode").value;
  const currentReference = mode === "reference";
  const oldReference = mode === "old-reference";
  $("#uploadTitle").textContent = currentReference ? "Select reference workbook" : "Select old inventory workbook";
  $("#uploadHelp").textContent = currentReference
    ? "Required headers: MAKE, COLOR, and START or END. START is preferred."
    : "Use an older workbook exported by this web app or the desktop version.";
  $("#referenceUploadField").classList.toggle("hidden", !oldReference);
  $("#selectedReferenceFile").classList.toggle("hidden", !oldReference);
  appState.comparisonFile = null;
  appState.referenceFile = null;
  $("#comparisonFile").value = "";
  $("#referenceFile").value = "";
  $("#selectedFile").textContent = "No workbook selected";
  $("#selectedReferenceFile").textContent = "No reference workbook selected";
}

function handleEntryKeyboard(event) {
  if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return;
  const order = ["model", "ram", "storage", "color", "itemsPerBox", "boxes", "looseItems", "area"];
  const current = order.indexOf(event.target.id);
  if (current < 0) return;
  if (event.target.id === "model" && !$("#modelSuggestions").classList.contains("hidden") && appState.catalogMatches.length) {
    event.preventDefault();
    selectCatalogVariant(appState.catalogActiveIndex >= 0 ? appState.catalogActiveIndex : 0);
    return;
  }
  event.preventDefault();
  if (current === order.length - 1) {
    $("#entryForm").requestSubmit();
    return;
  }
  document.getElementById(order[current + 1]).focus();
  document.getElementById(order[current + 1]).select?.();
}

function bindEvents() {
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => showPanel(tab.dataset.panel)));
  ["#itemsPerBox", "#boxes", "#looseItems"].forEach((selector) => $(selector).addEventListener("input", calculateAmount));
  $$("#entryForm input").forEach((input) => {
    input.addEventListener("input", saveFormDraft);
    input.addEventListener("change", saveFormDraft);
    input.addEventListener("keydown", handleEntryKeyboard);
  });
  $("#model").addEventListener("input", () => { clearSelectedInventoryQuantity(); queueModelSuggestions(); });
  $("#model").addEventListener("focus", queueModelSuggestions);
  ["#ram", "#storage", "#color"].forEach((selector) => $(selector).addEventListener("input", clearSelectedInventoryQuantity));
  $("#model").addEventListener("keydown", (event) => {
    if ($("#modelSuggestions").classList.contains("hidden")) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveCatalogOption(appState.catalogActiveIndex + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveCatalogOption(appState.catalogActiveIndex - 1);
    } else if (event.key === "Escape") {
      hideModelSuggestions();
    }
  });
  $("#modelSuggestions").addEventListener("click", (event) => {
    const option = event.target.closest("button[data-catalog-index]");
    if (option) selectCatalogVariant(Number(option.dataset.catalogIndex));
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".autocomplete-field")) hideModelSuggestions();
  });
  $("#entryForm").addEventListener("submit", (event) => { event.preventDefault(); saveEntry(false); });
  $("#cancelEditButton").addEventListener("click", () => { resetEntryForm(false); focusCountEntry(); });
  $("#entrySearch").addEventListener("input", () => { renderEntries(); saveFormDraft(); });
  $("#recentItemButtons").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-recent-id]");
    if (button) loadRecentItem(button.dataset.recentId);
  });
  $("#entryRows").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "edit") beginEdit(button.dataset.id);
    if (button.dataset.action === "delete") deleteEntry(button.dataset.id);
  });
  $("#quickNewCount").addEventListener("click", () => { showPanel("sessionsPanel"); $("#sessionName").focus(); });
  $("#quickContinue").addEventListener("click", focusCountEntry);
  $("#quickProblems").addEventListener("click", openProblems);
  $("#problemsButton").addEventListener("click", openProblems);
  $("#quickExport").addEventListener("click", exportWorkbook);
  $("#resumeFocusButton").addEventListener("click", focusCountEntry);
  $("#issuesOnly").addEventListener("change", (event) => {
    appState.issueOnly = Boolean(event.target.checked);
    renderComparisons();
    saveFormDraft();
  });
  $("#downloadLastWorkbook").addEventListener("click", () => window.location.assign("/api/reference/last/download"));
  $("#reuseLastReferenceButton").addEventListener("click", reuseLastReference);
  $("#comparisonMode").addEventListener("change", updateComparisonMode);
  $("#organizeFile").addEventListener("change", (event) => {
    appState.organizeFile = event.target.files[0] || null;
    $("#selectedOrganizeFile").textContent = appState.organizeFile
      ? `${appState.organizeFile.name} · ${(appState.organizeFile.size / 1024).toFixed(1)} KB`
      : "No workbook selected";
    $("#organizePreview").classList.add("hidden");
  });
  $("#organizeWorkbookButton").addEventListener("click", organizeWorkbook);
  $("#comparisonFile").addEventListener("change", (event) => {
    appState.comparisonFile = event.target.files[0] || null;
    $("#selectedFile").textContent = appState.comparisonFile
      ? `${appState.comparisonFile.name} · ${(appState.comparisonFile.size / 1024).toFixed(1)} KB`
      : "No workbook selected";
  });
  $("#referenceFile").addEventListener("change", (event) => {
    appState.referenceFile = event.target.files[0] || null;
    $("#selectedReferenceFile").textContent = appState.referenceFile
      ? `${appState.referenceFile.name} · ${(appState.referenceFile.size / 1024).toFixed(1)} KB`
      : "No reference workbook selected";
  });
  $("#runComparisonButton").addEventListener("click", runComparison);
  $("#copyIssuesButton").addEventListener("click", copyIssues);
  $("#newSessionForm").addEventListener("submit", (event) => {
    event.preventDefault();
    createSession({
      name: $("#sessionName").value.trim(), count_type: $("#sessionType").value,
      operator_name: $("#sessionOperator").value.trim(), warehouse: $("#sessionWarehouse").value.trim(),
      location: $("#sessionLocation").value.trim(), quantity_tolerance: $("#quantityTolerance").value,
      percentage_tolerance: $("#percentageTolerance").value,
    });
    $("#sessionName").value = "";
  });
  $("#sessionReferenceFile").addEventListener("change", (event) => {
    appState.sessionReferenceFile = event.target.files[0] || null;
    $("#selectedSessionReference").textContent = appState.sessionReferenceFile ? appState.sessionReferenceFile.name : "No reference workbook selected";
  });
  $("#freezeReferenceButton").addEventListener("click", freezeReference);
  $("#submitCountButton").addEventListener("click", submitCycleCount);
  $("#approveButton").addEventListener("click", () => reviewCycle("APPROVE"));
  $("#recountButton").addEventListener("click", () => reviewCycle("RECOUNT"));
  $("#movementForm").addEventListener("submit", (event) => { event.preventDefault(); saveMovement(); });
  $("#sessionRows").addEventListener("click", (event) => {
    const button = event.target.closest('button[data-action="activate-session"]');
    if (button) activateSession(button.dataset.id);
  });
  $("#finalizeButton").addEventListener("click", finalizeCurrentSession);
  $("#exportButton").addEventListener("click", exportWorkbook);
  $("#newSessionButton").addEventListener("click", () => {
    showPanel("sessionsPanel");
    $("#sessionName").focus();
  });
}

async function start() {
  bindEvents();
  calculateAmount();
  try {
    setBusy(true, "Loading inventory database…");
    await loadState();
  } catch (error) {
    toast("Could not load the application", error.message, "error");
  } finally {
    setBusy(false);
  }
}

document.addEventListener("DOMContentLoaded", start);
