const singleTab = document.getElementById("single-tab");
const batchTab = document.getElementById("batch-tab");
const singlePanel = document.getElementById("single-panel");
const batchPanel = document.getElementById("batch-panel");
const form = document.getElementById("verify-form");
const imageInput = document.getElementById("label-image");
const selectedFile = document.getElementById("selected-file");
const singleImagePreview = document.getElementById("single-image-preview");
const formMessage = document.getElementById("form-message");
const submitButton = document.getElementById("submit-button");
const batchItemsContainer = document.getElementById("batch-items");
const batchMessage = document.getElementById("batch-message");
const addBatchItemButton = document.getElementById("add-batch-item");
const batchSubmitButton = document.getElementById("batch-submit-button");
const loadingState = document.getElementById("loading-state");
const loadingTitle = document.getElementById("loading-title");
const loadingText = document.getElementById("loading-text");
const resultsSection = document.getElementById("results-section");
const verdictBanner = document.getElementById("verdict-banner");
const verdictText = document.getElementById("verdict-text");
const latencyText = document.getElementById("latency-text");
const fieldResults = document.getElementById("field-results");
const batchResultsSection = document.getElementById("batch-results-section");
const batchSummaryCounts = document.getElementById("batch-summary-counts");
const batchLatencyText = document.getElementById("batch-latency-text");
const batchResults = document.getElementById("batch-results");
const singleResetButton = document.getElementById("single-reset-button");
const batchResetButton = document.getElementById("batch-reset-button");

const fieldLabels = {
  brand_name: "Brand Name",
  product_class: "Product Class",
  producer_name: "Producer Name",
  country_of_origin: "Country of Origin",
  abv: "Alcohol %",
  net_contents: "Bottle Size",
  government_warning: "Government Warning",
};

const failReasons = {
  brand_name: "The label says something different.",
  product_class: "The label says something different.",
  producer_name: "The label says something different.",
  country_of_origin: "The countries do not match.",
  abv: "The alcohol numbers do not match closely enough.",
  net_contents: "The bottle sizes do not match.",
  government_warning: "The warning must match exactly, including capital letters and punctuation.",
};

const requiredFields = [
  "brand_name",
  "product_class",
  "producer_name",
  "country_of_origin",
  "abv",
  "net_contents",
  "government_warning",
];

const MAX_BATCH_ITEMS = 10;
let batchItemCounter = 0;
let loadingSlowTimer = null;

singleTab.addEventListener("click", () => setMode("single"));
batchTab.addEventListener("click", () => setMode("batch"));
addBatchItemButton.addEventListener("click", () => addBatchItem());
batchSubmitButton.addEventListener("click", submitBatch);
singleResetButton.addEventListener("click", resetSingleForm);
batchResetButton.addEventListener("click", resetBatchForm);

imageInput.addEventListener("change", () => {
  updateImagePreview(imageInput, selectedFile, singleImagePreview);
  hideMessage(formMessage);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage(formMessage);
  clearResults();

  const validationMessage = validateSingleForm();
  if (validationMessage) {
    showMessage(formMessage, validationMessage);
    return;
  }

  setLoading(true, "Checking the label...", "This may take a few seconds.");

  try {
    const response = await fetch("/verify", {
      method: "POST",
      body: buildSingleFormData(),
    });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(readableError(data));
    }

    renderSingleResults(data);
  } catch (error) {
    showMessage(formMessage, error.message || "Something went wrong. Please try again.");
  } finally {
    setLoading(false);
  }
});

function setMode(mode) {
  const isSingle = mode === "single";
  singleTab.classList.toggle("is-active", isSingle);
  batchTab.classList.toggle("is-active", !isSingle);
  singleTab.setAttribute("aria-selected", String(isSingle));
  batchTab.setAttribute("aria-selected", String(!isSingle));
  singlePanel.hidden = !isSingle;
  batchPanel.hidden = isSingle;
  clearResults();
  hideMessage(formMessage);
  hideMessage(batchMessage);
}

function validateSingleForm() {
  if (!imageInput.files.length) {
    return "Please choose a label image.";
  }

  for (const field of requiredFields) {
    const input = form.elements[field];
    if (!input.value.trim()) {
      return "Please fill in all fields before checking the label.";
    }
  }

  return "";
}

function buildSingleFormData() {
  const applicationData = readApplicationData(form);
  const formData = new FormData();
  formData.append("image", imageInput.files[0]);
  formData.append("application_data", JSON.stringify(applicationData));
  return formData;
}

function updateImagePreview(input, fileLabel, previewImage) {
  const file = input.files[0];
  if (previewImage.dataset.previewUrl) {
    URL.revokeObjectURL(previewImage.dataset.previewUrl);
    delete previewImage.dataset.previewUrl;
  }

  fileLabel.textContent = file ? file.name : "No image selected";
  if (!file) {
    previewImage.removeAttribute("src");
    previewImage.hidden = true;
    return;
  }

  const previewUrl = URL.createObjectURL(file);
  previewImage.src = previewUrl;
  previewImage.dataset.previewUrl = previewUrl;
  previewImage.hidden = false;
}

function readApplicationData(scope) {
  const applicationData = {};
  for (const field of requiredFields) {
    applicationData[field] = scope.querySelector(`[name="${field}"]`).value.trim();
  }
  return applicationData;
}

function addBatchItem() {
  hideMessage(batchMessage);
  if (batchItemsContainer.children.length >= MAX_BATCH_ITEMS) {
    showMessage(batchMessage, "Please check no more than 10 labels at once.");
    return;
  }

  batchItemCounter += 1;
  const item = document.createElement("article");
  const rowId = `batch-row-${batchItemCounter}`;
  const imageId = `${rowId}-image`;
  const warningId = `${rowId}-government-warning`;
  item.className = "batch-item";
  item.dataset.clientId = `label-${batchItemCounter}`;
  item.innerHTML = `
    <div class="batch-item-header">
      <h3>Label ${batchItemsContainer.children.length + 1}</h3>
      <button class="remove-button" type="button" aria-label="Remove this label">Remove</button>
    </div>
    <div class="field image-field">
      <label for="${imageId}">Label Image</label>
      <input id="${imageId}" name="image" type="file" accept="image/*">
      <div class="selected-file" aria-live="polite">No image selected</div>
      <img class="image-preview" alt="Selected label preview" hidden>
    </div>
    <div class="field-grid">
      ${batchTextField("brand_name", "Brand Name", rowId)}
      ${batchTextField("product_class", "Product Class", rowId)}
      ${batchTextField("producer_name", "Producer Name", rowId)}
      ${batchTextField("country_of_origin", "Country of Origin", rowId)}
      ${batchTextField("abv", "Alcohol %", rowId, "number", "0.1")}
      ${batchTextField("net_contents", "Bottle Size", rowId, "number", "1")}
    </div>
    <div class="field">
      <label for="${warningId}">Government Warning</label>
      <textarea id="${warningId}" name="government_warning" rows="5"></textarea>
    </div>
  `;

  const fileInput = item.querySelector('input[name="image"]');
  const fileName = item.querySelector(".selected-file");
  const previewImage = item.querySelector(".image-preview");
  fileInput.addEventListener("change", () => {
    updateImagePreview(fileInput, fileName, previewImage);
  });
  item.querySelector(".remove-button").addEventListener("click", () => {
    if (previewImage.dataset.previewUrl) {
      URL.revokeObjectURL(previewImage.dataset.previewUrl);
    }
    item.remove();
    renumberBatchItems();
  });
  batchItemsContainer.appendChild(item);
}

function batchTextField(name, label, rowId, type = "text", step = "") {
  const inputId = `${rowId}-${name.replaceAll("_", "-")}`;
  const numericAttributes = type === "number" ? ` step="${step}" inputmode="decimal"` : "";
  return `
    <div class="field">
      <label for="${inputId}">${label}</label>
      <input id="${inputId}" name="${name}" type="${type}"${numericAttributes} autocomplete="off">
    </div>
  `;
}

function renumberBatchItems() {
  [...batchItemsContainer.children].forEach((item, index) => {
    item.querySelector("h3").textContent = `Label ${index + 1}`;
  });
}

async function submitBatch() {
  hideMessage(batchMessage);
  clearResults();

  const buildResult = buildBatchFormData();
  if (buildResult.error) {
    showMessage(batchMessage, buildResult.error);
    return;
  }

  setLoading(true, "Checking labels...", `Checking ${buildResult.count} labels.`);

  try {
    const response = await fetch("/verify/batch", {
      method: "POST",
      body: buildResult.formData,
    });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(readableError(data));
    }

    renderBatchResults(data);
  } catch (error) {
    showMessage(batchMessage, error.message || "Something went wrong. Please try again.");
  } finally {
    setLoading(false);
  }
}

function buildBatchFormData() {
  const rows = [...batchItemsContainer.children];
  if (!rows.length) {
    return { error: "Please add at least one label." };
  }

  const formData = new FormData();
  const items = [];

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const image = row.querySelector('input[name="image"]');
    if (!image.files.length) {
      return { error: `Please choose an image for Label ${index + 1}.` };
    }

    for (const field of requiredFields) {
      const input = row.querySelector(`[name="${field}"]`);
      if (!input.value.trim()) {
        return { error: `Please fill in all fields for Label ${index + 1}.` };
      }
    }

    formData.append("images", image.files[0]);
    items.push({
      client_id: row.dataset.clientId,
      image_index: index,
      application_data: readApplicationData(row),
    });
  }

  formData.append("items", JSON.stringify(items));
  return { formData, count: rows.length };
}

function renderSingleResults(data) {
  const verification = data.verification;
  const verdict = verification.overall_verdict;
  const approved = verdict === "APPROVED";

  verdictText.textContent = approved ? "APPROVED" : "NEEDS REVIEW";
  verdictBanner.className = approved ? "verdict-banner verdict-pass" : "verdict-banner verdict-fail";
  latencyText.textContent = Number.isInteger(data.latency_ms)
    ? `Time: ${(data.latency_ms / 1000).toFixed(1)} seconds`
    : "";

  fieldResults.innerHTML = "";
  verification.fields.forEach((field) => {
    fieldResults.appendChild(renderFieldResult(field));
  });

  resultsSection.hidden = false;
  resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderBatchResults(data) {
  const summary = data.summary;
  batchSummaryCounts.innerHTML = "";
  batchSummaryCounts.append(
    summaryBox("Total", summary.total),
    summaryBox("Approved", summary.passed),
    summaryBox("Needs Review", summary.needs_review),
  );
  batchLatencyText.textContent = Number.isInteger(summary.latency_ms)
    ? `Time: ${(summary.latency_ms / 1000).toFixed(1)} seconds`
    : "";

  batchResults.innerHTML = "";
  data.results.forEach((result, index) => {
    batchResults.appendChild(renderBatchResult(result, index));
  });
  batchResultsSection.hidden = false;
  batchResultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function summaryBox(label, value) {
  const box = document.createElement("div");
  box.className = "summary-box";
  box.innerHTML = `<div class="summary-value">${value}</div><div class="summary-label">${label}</div>`;
  return box;
}

function renderBatchResult(result, index) {
  const item = document.createElement("article");
  item.className = "batch-result";

  const title = result.filename || `Label ${index + 1}`;
  const statusText = result.status === "FAILED"
    ? "COULD NOT PROCESS"
    : result.verification.overall_verdict === "APPROVED"
      ? "APPROVED"
      : "NEEDS REVIEW";
  const statusClass = result.status === "FAILED"
    ? "batch-status-failed"
    : result.verification.overall_verdict === "APPROVED"
      ? "batch-status-pass"
      : "batch-status-review";

  const detailsId = `batch-details-${index}`;
  item.innerHTML = `
    <div class="batch-result-header">
      <div>
        <h3>${escapeHtml(title)}</h3>
        <div class="batch-client-id">${escapeHtml(result.client_id)}</div>
      </div>
      <div class="batch-status ${statusClass}">${statusText}</div>
    </div>
    <button class="details-button" type="button" aria-expanded="false" aria-controls="${detailsId}">Show Details</button>
    <div id="${detailsId}" class="batch-detail-panel" hidden></div>
  `;

  const panel = item.querySelector(".batch-detail-panel");
  if (result.status === "FAILED") {
    const error = document.createElement("div");
    error.className = "message inline-message";
    error.textContent = result.error?.message || "Something went wrong. Please try again.";
    panel.appendChild(error);
  } else {
    result.verification.fields.forEach((field) => {
      panel.appendChild(renderFieldResult(field));
    });
  }

  const button = item.querySelector(".details-button");
  button.addEventListener("click", () => {
    const isOpen = !panel.hidden;
    panel.hidden = isOpen;
    button.setAttribute("aria-expanded", String(!isOpen));
    button.textContent = isOpen ? "Show Details" : "Hide Details";
  });

  return item;
}

function renderFieldResult(field) {
  const isPass = field.status === "PASS";
  const row = document.createElement("article");
  row.className = isPass ? "field-result result-pass" : "field-result result-fail";

  const header = document.createElement("div");
  header.className = "result-header";

  const name = document.createElement("h3");
  name.textContent = fieldLabels[field.field] || field.field;

  const status = document.createElement("span");
  status.className = "result-status";
  status.textContent = isPass ? "Matches" : "Needs review";

  header.append(name, status);
  row.appendChild(header);

  if (!isPass) {
    const reason = document.createElement("p");
    reason.className = "fail-reason";
    reason.textContent = failReasons[field.field] || "The label does not match the application.";
    row.appendChild(reason);

    row.appendChild(valueBlock("What the application says", field.expected));
    row.appendChild(valueBlock("What the label says", field.found));
  }

  return row;
}

function valueBlock(label, value) {
  const block = document.createElement("div");
  block.className = "value-block";

  const heading = document.createElement("div");
  heading.className = "value-label";
  heading.textContent = label;

  const content = document.createElement("div");
  content.className = "value-content";
  content.textContent = value === null || value === undefined || value === "" ? "Not found" : String(value);

  block.append(heading, content);
  return block;
}

function readableError(data) {
  return data?.detail?.error?.message || data?.error?.message || "Something went wrong. Please try again.";
}

function showMessage(target, message) {
  target.textContent = message;
  target.hidden = false;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideMessage(target) {
  target.textContent = "";
  target.hidden = true;
}

function clearResults() {
  resultsSection.hidden = true;
  batchResultsSection.hidden = true;
  fieldResults.innerHTML = "";
  batchResults.innerHTML = "";
}

function resetSingleForm() {
  form.reset();
  updateImagePreview(imageInput, selectedFile, singleImagePreview);
  hideMessage(formMessage);
  clearResults();
  imageInput.focus();
}

function resetBatchForm() {
  batchItemsContainer.querySelectorAll(".image-preview").forEach((previewImage) => {
    if (previewImage.dataset.previewUrl) {
      URL.revokeObjectURL(previewImage.dataset.previewUrl);
    }
  });
  batchItemsContainer.innerHTML = "";
  batchItemCounter = 0;
  addBatchItem();
  hideMessage(batchMessage);
  clearResults();
  batchItemsContainer.querySelector('input[name="image"]')?.focus();
}

function setLoading(isLoading, title = "Checking...", text = "This may take a few seconds.") {
  if (loadingSlowTimer) {
    window.clearTimeout(loadingSlowTimer);
    loadingSlowTimer = null;
  }

  submitButton.disabled = isLoading;
  batchSubmitButton.disabled = isLoading;
  addBatchItemButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "CHECKING..." : "CHECK LABEL";
  batchSubmitButton.textContent = isLoading ? "CHECKING..." : "CHECK ALL LABELS";
  loadingTitle.textContent = title;
  loadingText.textContent = text;
  loadingState.hidden = !isLoading;

  if (isLoading) {
    loadingSlowTimer = window.setTimeout(() => {
      loadingText.textContent = "First request after idle can take ~10 s while the server wakes up.";
    }, 3000);
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
  })[char]);
}

addBatchItem();