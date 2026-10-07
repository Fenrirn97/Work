const captureButton = document.getElementById("capture");
const diagnosticButton = document.getElementById("diagnostic");
const statusBox = document.getElementById("status");

function setStatus(message) {
  statusBox.textContent = message;
}

async function captureShipmentsGrid() {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const norm = (value) => clean(value).toLowerCase();
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) !== 0 && box.width > 0 && box.height > 0;
  };
  const allText = (el) => {
    if (!el) return "";
    const values = [
      el.innerText,
      el.textContent,
      el.getAttribute && el.getAttribute("aria-label"),
      el.getAttribute && el.getAttribute("title"),
      el.getAttribute && el.getAttribute("data-tooltip-content"),
      el.getAttribute && el.getAttribute("data-original-title")
    ];
    if (el.querySelectorAll) {
      for (const child of el.querySelectorAll("[aria-label],[title],[data-tooltip-content],[data-original-title],time")) {
        values.push(
          child.innerText,
          child.textContent,
          child.getAttribute("aria-label"),
          child.getAttribute("title"),
          child.getAttribute("data-tooltip-content"),
          child.getAttribute("data-original-title"),
          child.getAttribute("datetime")
        );
      }
    }
    return [...new Set(values.map(clean).filter(Boolean))].join(" | ");
  };

  const wantedHeaders = {
    shipment: ["shipment #", "shipment number"],
    order: ["order #", "order number"],
    tracking: ["tracking #", "tracking number"],
    label: ["label printed", "label print"]
  };

  const diagnostic = {
    pageUrl: location.href,
    pageTitle: document.title,
    capturedAt: new Date().toISOString(),
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio || 1
    },
    semanticHeaderTexts: [],
    headerMap: {},
    headerRects: {},
    horizontalScroller: null,
    verticalScroller: null
  };

  function smallestExactTextElement(names) {
    const matches = [];
    for (const el of document.querySelectorAll("body *")) {
      if (!visible(el)) continue;
      const text = norm(el.innerText || el.textContent || "");
      if (!names.includes(text)) continue;
      const box = el.getBoundingClientRect();
      if (box.bottom < 0 || box.top > window.innerHeight) continue;
      matches.push({el, box, area: box.width * box.height});
    }
    matches.sort((a, b) => a.area - b.area || a.box.top - b.box.top);
    return matches.length ? matches[0].el : null;
  }

  const semanticHeaders = [...document.querySelectorAll('[role="columnheader"], thead th')].filter(visible);
  diagnostic.semanticHeaderTexts = semanticHeaders.slice(0, 60).map((el) => clean(allText(el)));
  const headerMap = {};
  if (semanticHeaders.length) {
    for (const [key, names] of Object.entries(wantedHeaders)) {
      headerMap[key] = semanticHeaders.find((el) => {
        const text = norm(allText(el));
        return names.some((name) => text === name || text.includes(name));
      }) || null;
    }
  }
  for (const [key, names] of Object.entries(wantedHeaders)) {
    if (!headerMap[key]) headerMap[key] = smallestExactTextElement(names);
  }

  // ShipStation's Label Printed cell sits between these two columns. Finding the
  // neighbors lets us define the real cell boundaries instead of guessing from
  // the widely separated Tracking # column.
  const neighborHeaders = {
    packing: smallestExactTextElement(["packing slip printed"]),
    marketplace: smallestExactTextElement(["marketplace notified"])
  };

  diagnostic.headerMap = Object.fromEntries(
    Object.entries(headerMap).map(([key, el]) => [key, el ? clean(allText(el)) : "NOT FOUND"])
  );
  for (const [key, el] of Object.entries(headerMap)) {
    if (!el) continue;
    const r = el.getBoundingClientRect();
    diagnostic.headerRects[key] = {
      left: Math.round(r.left), top: Math.round(r.top), right: Math.round(r.right), bottom: Math.round(r.bottom),
      width: Math.round(r.width), height: Math.round(r.height)
    };
  }

  const missingHeaders = Object.entries(headerMap).filter(([, el]) => !el).map(([key]) => key);
  if (missingHeaders.length) {
    return {
      ok: false,
      reason: `Could not find these ShipStation columns: ${missingHeaders.join(", ")}. Use Columns in ShipStation to enable Shipment #, Order #, Tracking # and Label Printed.`,
      diagnostic
    };
  }

  function rectsAndCenters() {
    const rects = {};
    for (const [key, el] of Object.entries(headerMap)) rects[key] = el.getBoundingClientRect();
    return {
      rects,
      centers: Object.fromEntries(Object.entries(rects).map(([key, r]) => [key, r.left + r.width / 2])),
      headerBottom: Math.max(...Object.values(rects).map((r) => r.bottom))
    };
  }

  let geometry = rectsAndCenters();
  const ordered = Object.entries(geometry.centers).sort((a, b) => a[1] - b[1]);
  const bounds = {};
  for (let i = 0; i < ordered.length; i += 1) {
    const [key, x] = ordered[i];
    const prev = i > 0 ? ordered[i - 1][1] : x - Math.max(90, (ordered[i + 1]?.[1] || x + 180) - x);
    const next = i < ordered.length - 1 ? ordered[i + 1][1] : x + Math.max(120, x - (ordered[i - 1]?.[1] || x - 180));
    bounds[key] = {left: (prev + x) / 2, right: (x + next) / 2};
  }

  function centerOf(el) {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return r.left + r.width / 2;
  }

  function currentExactLabelBounds() {
    const labelCenter = centerOf(headerMap.label);
    const packingCenter = centerOf(neighborHeaders.packing);
    const marketplaceCenter = centerOf(neighborHeaders.marketplace);
    const fallback = bounds.label;
    return {
      left: Number.isFinite(packingCenter) ? (packingCenter + labelCenter) / 2 : fallback.left,
      right: Number.isFinite(marketplaceCenter) ? (labelCenter + marketplaceCenter) / 2 : fallback.right,
      center: labelCenter
    };
  }

  diagnostic.neighborHeaders = {
    packing: neighborHeaders.packing ? clean(allText(neighborHeaders.packing)) : "NOT FOUND",
    marketplace: neighborHeaders.marketplace ? clean(allText(neighborHeaders.marketplace)) : "NOT FOUND"
  };

  function textAtPoint(x, y, kind) {
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) return "";
    const elements = document.elementsFromPoint(x, y).filter(visible);
    const candidates = [];
    for (const el of elements) {
      const box = el.getBoundingClientRect();
      const text = allText(el);
      if (!text) continue;
      if (box.top > y + 4 || box.bottom < y - 4) continue;
      candidates.push({el, box, text, area: box.width * box.height});
    }

    const preferred = candidates.filter((item) => {
      const t = clean(item.text);
      if (kind === "shipment") return /^\d{6,12}$/.test(t);
      if (kind === "label") return /(?:^|[^A-Za-z])(?:not\s+printed|printed|created)(?=\s|\d|$)/i.test(t);
      if (kind === "tracking") return /[A-Z0-9]{8,}/i.test(t) && !/printed|created/i.test(t);
      if (kind === "order") return /[A-Z0-9][A-Z0-9-]{4,}/i.test(t) && !/printed|created/i.test(t);
      return true;
    });
    const list = preferred.length ? preferred : candidates;
    list.sort((a, b) => a.area - b.area);
    return list.length ? clean(list[0].text) : "";
  }

  function shipmentRowsInViewport() {
    const result = [];
    const seen = new Set();
    const column = bounds.shipment;
    const selectors = "a, [role='link'], span, div";
    for (const el of document.querySelectorAll(selectors)) {
      if (!visible(el)) continue;
      const text = clean(el.innerText || el.textContent || "");
      if (!/^\d{6,12}$/.test(text)) continue;
      const box = el.getBoundingClientRect();
      const cx = box.left + box.width / 2;
      const cy = box.top + box.height / 2;
      if (cy <= geometry.headerBottom + 2 || cy >= window.innerHeight - 8) continue;
      if (cx < column.left || cx > column.right) continue;
      const key = `${text}|${Math.round(cy)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      result.push({shipmentNumber: text, y: cy, element: el});
    }
    result.sort((a, b) => a.y - b.y);
    return result;
  }

  function horizontalScrollableAncestor(el) {
    let node = el && el.parentElement;
    while (node && node !== document.body && node !== document.documentElement) {
      const style = getComputedStyle(node);
      if (node.scrollWidth > node.clientWidth + 60 && ["auto", "scroll", "overlay"].includes(style.overflowX)) return node;
      node = node.parentElement;
    }
    // Fallback: ShipStation's custom grid may keep the horizontal scroller beside the header.
    const candidates = [...document.querySelectorAll("body *")].filter((candidate) => {
      if (!visible(candidate)) return false;
      const style = getComputedStyle(candidate);
      const box = candidate.getBoundingClientRect();
      return candidate.scrollWidth > candidate.clientWidth + 100 &&
        ["auto", "scroll", "overlay"].includes(style.overflowX) &&
        box.top <= geometry.headerBottom + 20 && box.bottom > geometry.headerBottom + 60;
    });
    candidates.sort((a, b) => (a.getBoundingClientRect().width * a.getBoundingClientRect().height) - (b.getBoundingClientRect().width * b.getBoundingClientRect().height));
    return candidates[0] || null;
  }

  const horizontalScroller = horizontalScrollableAncestor(headerMap.label);
  const originalHorizontalLeft = horizontalScroller ? horizontalScroller.scrollLeft : 0;
  diagnostic.horizontalScroller = horizontalScroller ? {
    tag: horizontalScroller.tagName,
    className: clean(horizontalScroller.className),
    clientWidth: horizontalScroller.clientWidth,
    scrollWidth: horizontalScroller.scrollWidth,
    originalScrollLeft: originalHorizontalLeft
  } : null;

  async function revealLabelColumn() {
    geometry = rectsAndCenters();
    let labelRect = geometry.rects.label;
    const margin = 36;
    if (!horizontalScroller) return labelRect.left >= 0 && labelRect.right <= window.innerWidth;

    if (labelRect.right > window.innerWidth - margin) {
      horizontalScroller.scrollLeft = Math.min(
        horizontalScroller.scrollWidth - horizontalScroller.clientWidth,
        horizontalScroller.scrollLeft + (labelRect.right - (window.innerWidth - margin))
      );
      await sleep(120);
    } else if (labelRect.left < margin) {
      horizontalScroller.scrollLeft = Math.max(0, horizontalScroller.scrollLeft - (margin - labelRect.left));
      await sleep(120);
    }
    geometry = rectsAndCenters();
    labelRect = geometry.rects.label;
    return labelRect.left >= 0 && labelRect.right <= window.innerWidth;
  }

  async function restoreIdentifierColumns() {
    if (!horizontalScroller) return;
    if (Math.abs(horizontalScroller.scrollLeft - originalHorizontalLeft) > 1) {
      horizontalScroller.scrollLeft = originalHorizontalLeft;
      await sleep(100);
      geometry = rectsAndCenters();
    }
  }

  function rowContainerForSeed(seedElement) {
    let node = seedElement;
    let best = null;
    for (let depth = 0; node && node !== document.body && node !== document.documentElement && depth < 14; depth += 1, node = node.parentElement) {
      const box = node.getBoundingClientRect();
      if (box.width >= 600 && box.height >= 20 && box.height <= 90) {
        best = node;
      } else if (best && box.height > 120) {
        break;
      }
    }
    return best;
  }

  function textFromRowColumn(rowElement, targetX, kind) {
    if (!rowElement || !Number.isFinite(targetX)) return {text: "", rect: null, candidateCount: 0};
    const rowBox = rowElement.getBoundingClientRect();
    const rowY = rowBox.top + rowBox.height / 2;
    const candidates = [];
    const nodes = [rowElement, ...rowElement.querySelectorAll("*")];
    for (const el of nodes) {
      if (!visible(el)) continue;
      const box = el.getBoundingClientRect();
      if (box.width <= 1 || box.height <= 1 || box.height > Math.max(96, rowBox.height * 2.2)) continue;
      if (box.bottom < rowY - 7 || box.top > rowY + 7) continue;
      const text = allText(el);
      if (!text) continue;
      const centerX = box.left + box.width / 2;
      const distance = Math.abs(centerX - targetX);
      if (distance > 230) continue;

      const t = clean(text);
      let preferred = false;
      if (kind === "shipment") preferred = /^\d{6,12}$/.test(t);
      else if (kind === "label") preferred = /(?:^|[^A-Za-z])(?:not\s+printed|printed|created)(?=\s|\d|$)/i.test(t) && t.length < 180;
      else if (kind === "tracking") preferred = /[A-Z0-9]{8,}/i.test(t) && !/printed|created/i.test(t) && t.length < 120;
      else if (kind === "order") preferred = /[A-Z0-9][A-Z0-9#()\- ]{3,}/i.test(t) && !/printed|created/i.test(t) && t.length < 160;

      const giantPenalty = t.length > 240 ? 100000 : 0;
      const preferencePenalty = preferred ? 0 : (kind === "label" ? 30000 : 5000);
      const score = giantPenalty + preferencePenalty + distance * 30 + box.width * box.height * 0.002 + t.length;
      candidates.push({text: t, box, score, preferred});
    }

    candidates.sort((a, b) => a.score - b.score);
    const chosen = candidates[0];
    return {
      text: chosen ? chosen.text : "",
      rect: chosen ? {
        left: Math.round(chosen.box.left), top: Math.round(chosen.box.top),
        right: Math.round(chosen.box.right), bottom: Math.round(chosen.box.bottom),
        width: Math.round(chosen.box.width), height: Math.round(chosen.box.height)
      } : null,
      candidateCount: candidates.length
    };
  }

  function reasonableLabelText(value) {
    const text = clean(value);
    if (!text || text.length > 220) return false;
    return /(?:^|[^A-Za-z])(?:not\s+printed|printed|created)(?=\s|\d|$)/i.test(text);
  }

  // ShipStation can render "Printed" and its timestamp as separate nested spans.
  // Reading one best-matching DOM node loses half of the cell. Instead, inspect
  // every text fragment whose rectangle falls inside the real Label Printed column
  // and reconstruct the status + timestamp from those fragments.
  function labelTextFromRowFragments(rowElement) {
    if (!rowElement) return {text: "", fragmentCount: 0, fragments: [], bounds: null};
    const rowBox = rowElement.getBoundingClientRect();
    const band = currentExactLabelBounds();
    const fragments = [];
    for (const el of [rowElement, ...rowElement.querySelectorAll("*")]) {
      const box = el.getBoundingClientRect();
      if (box.width <= 0 || box.height <= 0 || box.height > Math.max(100, rowBox.height * 2.5)) continue;
      if (box.bottom <= rowBox.top + 1 || box.top >= rowBox.bottom - 1) continue;
      const overlap = Math.min(box.right, band.right) - Math.max(box.left, band.left);
      if (overlap <= 1) continue;
      const text = clean([
        el.innerText, el.textContent,
        el.getAttribute && el.getAttribute("aria-label"),
        el.getAttribute && el.getAttribute("title"),
        el.getAttribute && el.getAttribute("data-tooltip-content")
      ].filter(Boolean).join(" "));
      if (!text || text.length > 500) continue;
      if (!/printed|created|\d{1,2}\/\d{1,2}\/\d{4}|\d{1,2}:\d{2}/i.test(text)) continue;
      fragments.push({
        text, left: box.left, top: box.top, width: box.width, height: box.height,
        area: box.width * box.height
      });
    }

    // Prefer the smallest elements: parents often repeat all of their children's text.
    fragments.sort((a, b) => a.area - b.area || a.top - b.top || a.left - b.left);
    let status = "";
    let stamp = "";
    for (const item of fragments) {
      if (!status) {
        const m = item.text.match(/(?:^|[^A-Za-z])(not\s+printed|printed|created)(?=\s|\d|$)/i);
        if (m) status = m[1].replace(/\s+/g, " ");
      }
      if (!stamp) {
        const m = item.text.match(/(\d{1,2}\/\d{1,2}\/\d{4})\s*(?:[•·]|:|\s)\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)/i);
        if (m) stamp = `${m[1]}•${m[2]}`;
      }
      if (status && stamp) break;
    }

    // A single small node may already contain the complete value.
    if (!status || !stamp) {
      for (const item of fragments) {
        const combined = item.text;
        if (!status) {
          const m = combined.match(/(?:^|[^A-Za-z])(not\s+printed|printed|created)(?=\s|\d|$)/i);
          if (m) status = m[1].replace(/\s+/g, " ");
        }
        if (!stamp) {
          const m = combined.match(/(\d{1,2}\/\d{1,2}\/\d{4})\s*(?:[•·]|:|\s)\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)/i);
          if (m) stamp = `${m[1]}•${m[2]}`;
        }
      }
    }

    const text = clean([status, stamp].filter(Boolean).join(" "));
    return {
      text: reasonableLabelText(text) ? text : "",
      fragmentCount: fragments.length,
      fragments: fragments.slice(0, 12).map((f) => f.text),
      bounds: {left: Math.round(band.left), right: Math.round(band.right), center: Math.round(band.center)}
    };
  }

  const rowsByIdentity = new Map();

  async function collectCurrentViewport() {
    await restoreIdentifierColumns();
    geometry = rectsAndCenters();
    const rowSeeds = shipmentRowsInViewport();
    if (!rowSeeds.length) return [];

    // Read each shipment from its own row container. getBoundingClientRect() works for
    // off-screen cells too, so this avoids mistaking ShipStation's whole virtual-grid wrapper
    // for the Label Printed cell.
    const records = rowSeeds.map((seed) => {
      const rowElement = rowContainerForSeed(seed.element);
      const shipmentCell = textFromRowColumn(rowElement, geometry.centers.shipment, "shipment");
      const orderCell = textFromRowColumn(rowElement, geometry.centers.order, "order");
      const trackingCell = textFromRowColumn(rowElement, geometry.centers.tracking, "tracking");
      const labelFragments = labelTextFromRowFragments(rowElement);
      return {
        shipmentNumber: seed.shipmentNumber || shipmentCell.text || textAtPoint(geometry.centers.shipment, seed.y, "shipment"),
        orderNumber: orderCell.text || textAtPoint(geometry.centers.order, seed.y, "order"),
        tracking: trackingCell.text || textAtPoint(geometry.centers.tracking, seed.y, "tracking"),
        labelPrintedRaw: labelFragments.text,
        y: seed.y,
        rowElement,
        labelCandidateRect: labelFragments.bounds,
        labelCandidateCount: labelFragments.fragmentCount,
        labelFragments: labelFragments.fragments
      };
    });

    // Fallback: if a row-specific off-screen cell was not readable, temporarily reveal
    // Label Printed and read only that row's Y coordinate. Reject giant container text.
    const missingLabel = records.some((record) => !reasonableLabelText(record.labelPrintedRaw));
    if (missingLabel) {
      const labelVisible = await revealLabelColumn();
      if (labelVisible) {
        geometry = rectsAndCenters();
        const currentRows = [...document.querySelectorAll("[class*='grid-rows-']")].filter((el) => {
          const r = el.getBoundingClientRect();
          return r.height >= 20 && r.height <= 90 && r.width >= 500;
        });
        for (const record of records) {
          if (reasonableLabelText(record.labelPrintedRaw)) continue;
          let nearest = null;
          let nearestDistance = Infinity;
          for (const rowEl of currentRows) {
            const r = rowEl.getBoundingClientRect();
            const cy = r.top + r.height / 2;
            const d = Math.abs(cy - record.y);
            if (d < nearestDistance) { nearest = rowEl; nearestDistance = d; }
          }
          if (nearest && nearestDistance < 8) {
            const rebuilt = labelTextFromRowFragments(nearest);
            if (reasonableLabelText(rebuilt.text)) {
              record.labelPrintedRaw = rebuilt.text;
              record.labelCandidateRect = rebuilt.bounds;
              record.labelCandidateCount = rebuilt.fragmentCount;
              record.labelFragments = rebuilt.fragments;
              continue;
            }
          }
          const value = textAtPoint(geometry.centers.label, record.y, "label");
          if (reasonableLabelText(value)) record.labelPrintedRaw = value;
        }
      }
      await restoreIdentifierColumns();
    }

    for (const record of records) {
      const rowBox = record.rowElement && record.rowElement.getBoundingClientRect ? record.rowElement.getBoundingClientRect() : null;
      record.debug = {
        rowRect: rowBox ? {
          left: Math.round(rowBox.left), top: Math.round(rowBox.top), right: Math.round(rowBox.right), bottom: Math.round(rowBox.bottom),
          width: Math.round(rowBox.width), height: Math.round(rowBox.height)
        } : null,
        rowClass: record.rowElement ? clean(record.rowElement.className) : "",
        labelCandidateRect: record.labelCandidateRect || null,
        labelCandidateCount: record.labelCandidateCount || 0,
        labelFragments: record.labelFragments || []
      };
      delete record.y;
      delete record.rowElement;
      delete record.labelCandidateRect;
      delete record.labelCandidateCount;
      delete record.labelFragments;
      for (const key of ["shipmentNumber", "orderNumber", "tracking", "labelPrintedRaw"]) record[key] = clean(record[key]);
      if (!record.shipmentNumber) continue;
      const identity = record.shipmentNumber || record.tracking || record.orderNumber;
      const old = rowsByIdentity.get(identity);
      const score = (r) => [r.shipmentNumber, r.orderNumber, r.tracking, r.labelPrintedRaw].filter(Boolean).length + (/(?:^|[^A-Za-z])printed(?=\s|\d|$)/i.test(r.labelPrintedRaw || "") ? 2 : 0);
      if (!old || score(record) >= score(old)) rowsByIdentity.set(identity, record);
    }
    return rowSeeds;
  }

  let rowSeeds = await collectCurrentViewport();
  if (!rowSeeds.length) {
    return {ok: false, reason: "The columns were found, but no Shipment # rows were readable. Keep the shipment rows visible and try again.", diagnostic};
  }

  function verticalScrollableAncestor(el) {
    let node = el;
    while (node && node !== document.body && node !== document.documentElement) {
      if (node.scrollHeight > node.clientHeight + 80) {
        const style = getComputedStyle(node);
        if (["auto", "scroll", "overlay"].includes(style.overflowY)) return node;
      }
      node = node.parentElement;
    }
    const doc = document.scrollingElement || document.documentElement;
    return doc.scrollHeight > doc.clientHeight + 80 ? doc : null;
  }

  const verticalScroller = verticalScrollableAncestor(rowSeeds[0].element);
  diagnostic.verticalScroller = verticalScroller ? {
    tag: verticalScroller.tagName,
    className: clean(verticalScroller.className),
    clientHeight: verticalScroller.clientHeight,
    scrollHeight: verticalScroller.scrollHeight,
    originalScrollTop: verticalScroller.scrollTop
  } : null;
  if (verticalScroller) {
    const originalTop = verticalScroller.scrollTop;
    // Always scan the complete ShipStation grid from the top. The user may click
    // the extension while scrolled near the bottom, and starting there would miss
    // earlier shipments in ShipStation's virtualized list.
    verticalScroller.scrollTop = 0;
    await sleep(180);
    await collectCurrentViewport();

    const viewport = verticalScroller === document.scrollingElement || verticalScroller === document.documentElement ? window.innerHeight : verticalScroller.clientHeight;
    const step = Math.max(260, Math.floor(viewport * 0.72));
    let previousTop = -1;
    let stableBottom = 0;

    for (let loop = 0; loop < 220; loop += 1) {
      const maxTop = Math.max(0, verticalScroller.scrollHeight - (verticalScroller.clientHeight || window.innerHeight));
      const nextTop = Math.min(maxTop, verticalScroller.scrollTop + step);
      if (nextTop === previousTop) stableBottom += 1; else stableBottom = 0;
      previousTop = nextTop;
      verticalScroller.scrollTop = nextTop;
      await sleep(170);
      await collectCurrentViewport();
      const atBottom = verticalScroller.scrollTop >= maxTop - 4;
      if (atBottom && stableBottom >= 1) break;
      if (atBottom) stableBottom += 1;
      if (stableBottom >= 3) break;
    }

    verticalScroller.scrollTop = originalTop;
    await restoreIdentifierColumns();
    await sleep(80);
  }

  const rows = [...rowsByIdentity.values()];
  const labelReadCount = rows.filter((row) => clean(row.labelPrintedRaw)).length;
  diagnostic.finalHorizontalScrollLeft = horizontalScroller ? horizontalScroller.scrollLeft : null;
  diagnostic.rowCount = rows.length;
  diagnostic.labelReadCount = labelReadCount;

  return {
    ok: true,
    headers: Object.fromEntries(Object.entries(headerMap).map(([key, el]) => [key, clean(el.innerText || el.textContent || "")])),
    rows,
    labelReadCount,
    method: horizontalScroller ? "visible-text geometry + horizontal grid scroll" : (semanticHeaders.length ? "semantic + geometry fallback" : "visible-text geometry"),
    diagnostic
  };
}


function parseLabelForDiagnostic(rawValue) {
  const raw = String(rawValue || "").replace(/\s+/g, " ").trim();
  if (!raw) return {status: "Could not read", displayedTime: ""};
  if (/(?:^|[^A-Za-z])not\s+printed(?=\s|\d|$)/i.test(raw)) return {status: "Not Printed", displayedTime: ""};
  if (/(?:^|[^A-Za-z])printed(?=\s|\d|$)/i.test(raw)) {
    const match = raw.match(/(\d{1,2}\/\d{1,2}\/\d{4})\s*(?:[•·]|:|\s)\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)/i);
    return {status: "Printed", displayedTime: match ? `${match[1]} ${match[2]}` : ""};
  }
  if (/(?:^|[^A-Za-z])created(?=\s|\d|$)/i.test(raw)) return {status: "Created / Not Printed", displayedTime: ""};
  return {status: "Could not read", displayedTime: ""};
}

function diagnosticText(capture, tabUrl) {
  const lines = [];
  const debug = (capture && capture.diagnostic) || {};
  lines.push("SHIPSTATION PRINT TIME CAPTURE - DIAGNOSTIC TXT");
  lines.push("Extension version: 0.4.9");
  lines.push(`Generated: ${new Date().toISOString()}`);
  lines.push(`Tab URL: ${tabUrl || debug.pageUrl || ""}`);
  lines.push(`Page title: ${debug.pageTitle || ""}`);
  lines.push(`Capture OK: ${capture && capture.ok ? "YES" : "NO"}`);
  lines.push(`Reader method: ${(capture && capture.method) || ""}`);
  lines.push(`Failure reason: ${(capture && capture.reason) || ""}`);
  lines.push("");
  lines.push("--- VIEWPORT ---");
  lines.push(`Width: ${debug.viewport?.width ?? ""}`);
  lines.push(`Height: ${debug.viewport?.height ?? ""}`);
  lines.push(`Device pixel ratio: ${debug.viewport?.devicePixelRatio ?? ""}`);
  lines.push("");
  lines.push("--- DETECTED HEADERS ---");
  const headers = (capture && capture.headers) || debug.headerMap || {};
  for (const key of ["shipment", "order", "tracking", "label"]) {
    lines.push(`${key}: ${headers[key] || "NOT FOUND"}`);
  }
  lines.push(`packing neighbor: ${debug.neighborHeaders?.packing || "NOT FOUND"}`);
  lines.push(`marketplace neighbor: ${debug.neighborHeaders?.marketplace || "NOT FOUND"}`);
  lines.push("");
  lines.push("Header rectangles (screen CSS pixels):");
  for (const [key, value] of Object.entries(debug.headerRects || {})) {
    lines.push(`${key}: ${JSON.stringify(value)}`);
  }
  lines.push("");
  lines.push("Semantic table/grid headers found by browser:");
  if ((debug.semanticHeaderTexts || []).length) {
    for (const value of debug.semanticHeaderTexts) lines.push(`- ${value}`);
  } else {
    lines.push("- NONE");
  }
  lines.push("");
  lines.push("--- SCROLLERS ---");
  lines.push(`Horizontal: ${debug.horizontalScroller ? JSON.stringify(debug.horizontalScroller) : "NOT FOUND"}`);
  lines.push(`Vertical: ${debug.verticalScroller ? JSON.stringify(debug.verticalScroller) : "NOT FOUND"}`);
  lines.push(`Final horizontal scrollLeft: ${debug.finalHorizontalScrollLeft ?? ""}`);
  lines.push("");
  const rows = (capture && capture.rows) || [];
  const labelReadCount = capture && Number.isFinite(capture.labelReadCount) ? capture.labelReadCount : 0;
  lines.push("--- SUMMARY ---");
  lines.push(`Rows captured: ${rows.length}`);
  lines.push(`Rows with nonblank Label Printed raw text: ${labelReadCount}`);
  lines.push(`Rows with blank Label Printed raw text: ${Math.max(0, rows.length - labelReadCount)}`);
  lines.push("");
  lines.push("--- ROWS ---");
  if (!rows.length) {
    lines.push("NO ROWS CAPTURED");
  } else {
    rows.forEach((row, index) => {
      const parsed = parseLabelForDiagnostic(row.labelPrintedRaw);
      lines.push(`[${index + 1}]`);
      lines.push(`Shipment #: ${row.shipmentNumber || ""}`);
      lines.push(`Order #: ${row.orderNumber || ""}`);
      lines.push(`Tracking #: ${row.tracking || ""}`);
      lines.push(`Raw Label Printed: ${row.labelPrintedRaw || "<BLANK>"}`);
      lines.push(`Parsed status: ${parsed.status}`);
      lines.push(`Parsed displayed print time: ${parsed.displayedTime || "<BLANK>"}`);
      lines.push(`Row debug: ${row.debug ? JSON.stringify(row.debug) : "<NONE>"}`);
      lines.push("");
    });
  }
  lines.push("--- END DIAGNOSTIC ---");
  return lines.join("\r\n");
}

async function downloadDiagnosticFile(capture, tabUrl) {
  const now = new Date();
  const stamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
    "_",
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0")
  ].join("");
  const blob = new Blob([diagnosticText(capture, tabUrl)], {type: "text/plain;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  try {
    await chrome.downloads.download({
      url,
      filename: `ShipStation_Print_Time_Diagnostic_${stamp}.txt`,
      saveAs: true
    });
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }
}

async function getActiveShipStationTab() {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  if (!tab || !tab.id || !/^https:\/\/[^/]*shipstation\.com\//i.test(tab.url || "")) {
    throw new Error("Open the ShipStation Shipments page in this tab first.");
  }
  return tab;
}

async function readCurrentShipStationPage(tab) {
  const result = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: captureShipmentsGrid});
  return result && result[0] && result[0].result;
}

captureButton.addEventListener("click", async () => {
  captureButton.disabled = true;
  setStatus("Reading the current ShipStation Shipments page...");
  try {
    const tab = await getActiveShipStationTab();
    const capture = await readCurrentShipStationPage(tab);
    if (!capture || !capture.ok) throw new Error((capture && capture.reason) || "Could not read the ShipStation grid.");
    if (!capture.rows.length) throw new Error("No shipment rows were found on the current page.");

    const tokenResponse = await fetch("http://127.0.0.1:8787/api/extension-token", {cache: "no-store"});
    if (!tokenResponse.ok) throw new Error("The local ShipStation checker is not running.");
    const tokenData = await tokenResponse.json();
    const capturedAt = new Date().toISOString();
    const sendResponse = await fetch("http://127.0.0.1:8787/api/shipstation-print-capture", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-ShipStation-Capture-Token": tokenData.token},
      body: JSON.stringify({rows: capture.rows, capturedAt})
    });
    const data = await sendResponse.json();
    if (!sendResponse.ok) throw new Error(data.error || "The local checker rejected the capture.");
    const warning = capture.labelReadCount < capture.rows.length
      ? `\nWarning: Label Printed was readable for ${capture.labelReadCount} of ${capture.rows.length} rows.`
      : `\nLabel Printed read for all ${capture.rows.length} rows.`;
    setStatus(`Captured ${data.received} row(s).\nLocal checker now has ${data.total} unique row(s).${warning}\nReader: ${capture.method}.`);
  } catch (error) {
    setStatus(error && error.message ? error.message : "Capture failed.");
  } finally {
    captureButton.disabled = false;
  }
});


diagnosticButton.addEventListener("click", async () => {
  captureButton.disabled = true;
  diagnosticButton.disabled = true;
  setStatus("Reading ShipStation and building diagnostic TXT...");
  try {
    const tab = await getActiveShipStationTab();
    let capture;
    try {
      capture = await readCurrentShipStationPage(tab);
    } catch (error) {
      capture = {ok: false, reason: error && error.message ? error.message : "Page reader failed before returning data."};
    }
    await downloadDiagnosticFile(capture || {ok: false, reason: "No result returned by page reader."}, tab.url || "");
    const rows = capture && capture.rows ? capture.rows.length : 0;
    const readable = capture && Number.isFinite(capture.labelReadCount) ? capture.labelReadCount : 0;
    setStatus(`Diagnostic TXT downloaded.\nRows captured: ${rows}.\nLabel Printed readable: ${readable}.\nSend me that TXT file for troubleshooting.`);
  } catch (error) {
    setStatus(error && error.message ? error.message : "Diagnostic export failed.");
  } finally {
    captureButton.disabled = false;
    diagnosticButton.disabled = false;
  }
});
