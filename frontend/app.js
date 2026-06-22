async function loadHealth() {
  const output = document.getElementById("health-output");

  try {
    const response = await fetch("/health", { headers: { Accept: "application/json" } });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || `Health check failed with ${response.status}`);
    }

    output.textContent = JSON.stringify(data, null, 2);
    output.classList.add("is-ok");
  } catch (error) {
    output.textContent = `Unable to reach backend: ${error.message}`;
    output.classList.add("is-error");
  }
}

loadHealth();
