const form = document.getElementById("verify-form");
const imageInput = document.getElementById("label-image");
const selectedFile = document.getElementById("selected-file");
const formMessage = document.getElementById("form-message");
const submitButton = document.getElementById("submit-button");
const loadingState = document.getElementById("loading-state");
const resultsSection = document.getElementById("results-section");
const verdictBanner = document.getElementById("verdict-banner");
const verdictText = document.getElementById("verdict-text");
const latencyText = document.getElementById("latency-text");
const fieldResults = document.getElementById("field-results");

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

imageInput.addEventListener("change", () => {
  selectedFile.textContent = imageInput.files.length ? imageInput.files[0].name : "No image selected";
  hideMessage();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage();
  clearResults();

  const validationMessage = validateForm();
  if (validationMessage) {
    showMessage(validationMessage);
    return;
  }

  setLoading(true);

  try {
    const response = await fetch("/verify", {
      method: "POST",
      body: buildFormData(),
    });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(readableError(data));
    }

    renderResults(data);
  } catch (error) {
    showMessage(error.message || "Something went wrong. Please try again.");
  } finally {
    setLoading(false);
  }
});

function validateForm() {
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

function buildFormData() {
  const applicationData = {};
  for (const field of requiredFields) {
    applicationData[field] = form.elements[field].value.trim();
  }

  const formData = new FormData();
  formData.append("image", imageInput.files[0]);
  formData.append("application_data", JSON.stringify(applicationData));
  return formData;
}

function renderResults(data) {
  const verification = data.verification;
  const verdict = verification.verdict;
  const approved = verdict === "PASS";

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
  resultsSection.focus({ preventScroll: true });
  resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
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

    row.appendChild(valueBlock("What the application says", field.application_value));
    row.appendChild(valueBlock("What the label says", field.extracted_value));
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

function showMessage(message) {
  formMessage.textContent = message;
  formMessage.hidden = false;
  formMessage.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideMessage() {
  formMessage.textContent = "";
  formMessage.hidden = true;
}

function clearResults() {
  resultsSection.hidden = true;
  fieldResults.innerHTML = "";
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "CHECKING..." : "CHECK LABEL";
  loadingState.hidden = !isLoading;
}