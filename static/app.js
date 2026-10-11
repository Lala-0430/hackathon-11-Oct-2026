const LABEL_COLORS = {
  "Very Weak": "var(--very-weak)",
  "Weak": "var(--weak)",
  "Fair": "var(--fair)",
  "Strong": "var(--strong)",
  "Very Strong": "var(--very-strong)",
};

const $ = (id) => document.getElementById(id);
const steps = ["step-password", "step-questions", "step-result"];

let questions = [];
let assessmentId = null;

function showStep(id) {
  for (const s of steps) $(s).classList.toggle("hidden", s !== id);
}

function fillList(el, items) {
  el.replaceChildren(...items.map((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    return li;
  }));
}

async function loadQuestions() {
  const res = await fetch("/api/questions");
  questions = await res.json();
  $("question-list").replaceChildren(...questions.map((q) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="question-text"></div>
      <div class="yes-no">
        <label><input type="radio" name="${q.id}" value="yes" required> Yes</label>
        <label><input type="radio" name="${q.id}" value="no"> No</label>
      </div>`;
    li.querySelector(".question-text").textContent = q.text;
    return li;
  }));
}

$("toggle-visibility").addEventListener("click", () => {
  const input = $("password");
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  $("toggle-visibility").textContent = show ? "Hide" : "Show";
});

$("password-form").addEventListener("submit", (e) => {
  e.preventDefault();
  showStep("step-questions");
});

$("back").addEventListener("click", () => showStep("step-password"));

$("questions-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const answers = {};
  for (const q of questions) answers[q.id] = form.get(q.id) === "yes";

  const res = await fetch("/api/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: $("password").value, answers }),
  });
  if (!res.ok) {
    alert("Something went wrong. Please try again.");
    return;
  }
  renderResult(await res.json());
});

function renderResult(r) {
  assessmentId = r.id;
  const color = LABEL_COLORS[r.label];
  $("result-label").textContent = r.label;
  $("result-label").style.color = color;
  $("result-score").textContent = `${r.score} / 100`;
  $("meter-fill").style.width = `${r.score}%`;
  $("meter-fill").style.background = color;
  $("crack-time").textContent = r.crack_time_display;

  $("issues-block").classList.toggle("hidden", r.issues.length === 0);
  fillList($("issues"), r.issues);
  fillList($("tips"), r.tips);

  $("ai-block").classList.toggle("hidden", !r.ai_advice_available);
  $("ai-advice").classList.add("hidden");
  $("ai-button").disabled = false;

  document.querySelectorAll("[data-feedback]").forEach((b) => {
    b.disabled = false;
    b.classList.remove("selected");
  });
  $("feedback-thanks").classList.add("hidden");

  showStep("step-result");
}

$("ai-button").addEventListener("click", async () => {
  const btn = $("ai-button");
  const box = $("ai-advice");
  btn.disabled = true;
  box.classList.remove("hidden");
  box.textContent = "Thinking…";
  try {
    const res = await fetch(`/api/assessments/${assessmentId}/advice`, { method: "POST" });
    const data = await res.json();
    box.textContent = res.ok ? data.advice : `Could not get advice: ${data.detail}`;
  } catch {
    box.textContent = "Could not reach the server.";
  }
});

document.querySelectorAll("[data-feedback]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    await fetch(`/api/assessments/${assessmentId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback: btn.dataset.feedback }),
    });
    document.querySelectorAll("[data-feedback]").forEach((b) => (b.disabled = true));
    btn.classList.add("selected");
    $("feedback-thanks").classList.remove("hidden");
  });
});

$("restart").addEventListener("click", () => {
  $("password").value = "";
  $("questions-form").reset();
  assessmentId = null;
  showStep("step-password");
  $("password").focus();
});

loadQuestions();
