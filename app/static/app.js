const form = document.getElementById("queryForm");
const modelSelect = document.getElementById("modelSelect");
const queryInput = document.getElementById("queryInput");
const evidenceInput = document.getElementById("evidenceInput");
const evidenceError = document.getElementById("evidenceError");
const conversation = document.getElementById("conversation");
const submitButton = document.getElementById("submitButton");
const clearButton = document.getElementById("clearButton");
const stageOutputs = document.getElementById("stageOutputs");
const statusBadge = document.getElementById("statusBadge");
const resultMessage = document.getElementById("resultMessage");
const clarificationHint = document.getElementById("clarificationHint");

const defaultEvidence = {
  attribute_master_tables: {},
  distinct_database_values: {
    city_name: ["Pune"],
    property_type: ["residential"],
    transaction_category: ["sale"]
  },
  lookup_results: {}
};

evidenceInput.value = JSON.stringify(defaultEvidence, null, 2);

function appendBubble(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  conversation.appendChild(bubble);
  conversation.scrollTop = conversation.scrollHeight;
}

function setStatus(status, message) {
  statusBadge.className = `badge ${status}`;
  statusBadge.textContent = status.replaceAll("_", " ");
  resultMessage.textContent = message;
}

function parseEvidence() {
  evidenceError.classList.add("hidden");
  try {
    return JSON.parse(evidenceInput.value);
  } catch (error) {
    evidenceError.textContent = "Semantic context must contain valid JSON.";
    evidenceError.classList.remove("hidden");
    return null;
  }
}

function renderStages(data) {
  stageOutputs.replaceChildren();
  const outputs = data.stages || {};
  Object.entries(outputs).forEach(([stageName, value]) => {
    const details = document.createElement("details");
    details.open = stageName === "stage_3" || stageName === "stage_3_1";
    const summary = document.createElement("summary");
    summary.textContent = stageName.replaceAll("_", ".");
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(value, null, 2);
    details.append(summary, pre);
    stageOutputs.appendChild(details);
  });
}

function showClarification(data) {
  const stage = data.stopped_at_stage ? ` (${data.stopped_at_stage.replaceAll("_", ".")})` : "";
  const question = data.clarification_question || "Please clarify the requested values.";
  appendBubble("assistant", `Clarification required${stage}: ${question}`);
  clarificationHint.textContent =
    "Edit your complete query below to include this answer, then run the pipeline again.";
  clarificationHint.classList.remove("hidden");
  queryInput.focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  const semanticContext = parseEvidence();
  if (!query || !semanticContext) {
    return;
  }

  appendBubble("user", query);
  clarificationHint.classList.add("hidden");
  const modelLabel = modelSelect.options[modelSelect.selectedIndex].text;
  setStatus("running", `Running the sequential agent pipeline with ${modelLabel}...`);
  submitButton.disabled = true;
  modelSelect.disabled = true;
  submitButton.textContent = "Running...";

  try {
    const response = await fetch("/api/v1/sql/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        model: modelSelect.value,
        include_intermediate_stages: true,
        semantic_context: semanticContext
      })
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(JSON.stringify(data, null, 2));
    }

    renderStages(data);
    setStatus(data.pipeline_status, data.message);
    if (data.pipeline_status === "needs_clarification") {
      showClarification(data);
    } else if (data.pipeline_status === "completed") {
      appendBubble("assistant", "SQL was generated and approved. See the Stage 3 and SQL Review panels.");
    } else {
      appendBubble("assistant", data.message);
    }
  } catch (error) {
    setStatus("error", "The API request failed.");
    appendBubble("assistant", `Request failed: ${error.message}`);
  } finally {
    submitButton.disabled = false;
    modelSelect.disabled = false;
    submitButton.textContent = "Run Pipeline";
  }
});

clearButton.addEventListener("click", () => {
  queryInput.value = "";
  stageOutputs.replaceChildren();
  clarificationHint.classList.add("hidden");
  conversation.innerHTML = "";
  appendBubble(
    "assistant",
    "Start a new query. Include metric, location, property type, transaction category, and period."
  );
  setStatus("idle", "Completed stages will appear here as JSON.");
});
