const LABEL_COLORS = {
  "Very Weak": "var(--very-weak)",
  "Weak": "var(--weak)",
  "Fair": "var(--fair)",
  "Strong": "var(--strong)",
  "Very Strong": "var(--very-strong)",
};

const LABEL_SUMMARIES = {
  "Very Weak": "This password could be guessed almost instantly. Please choose a new one.",
  "Weak": "This password is easy to crack. Follow the tips below to make it stronger.",
  "Fair": "Your password is okay, but there are some clear ways to improve it.",
  "Strong": "Your password is strong, but there are a few things you can improve.",
  "Very Strong": "Excellent! Your password is very hard to crack.",
};

const RING_CIRCUMFERENCE = 2 * Math.PI * 50;

const $ = (id) => document.getElementById(id);
const steps = ["step-password", "step-questions", "step-result"];
const views = ["home", "checker", "generator", "about"];

let questions = [];
let assessmentId = null;

/* ---------- Navigation ---------- */

function showView(name) {
  for (const v of views) $(`view-${v}`).classList.toggle("hidden", v !== name);
  document.querySelectorAll(".nav-item").forEach((a) => {
    a.classList.toggle("active", a.dataset.view === name);
  });
  closeMenu();
  window.scrollTo({ top: 0 });
  if (name === "generator" && !$("gen-output").value) generatePassword();
}

function showStep(id) {
  const index = steps.indexOf(id);
  for (const s of steps) $(s).classList.toggle("hidden", s !== id);
  document.querySelectorAll("#stepper li").forEach((li) => {
    const n = Number(li.dataset.step);
    li.classList.toggle("active", n === index);
    li.classList.toggle("done", n < index || (index === steps.length - 1 && n === index));
  });
  window.scrollTo({ top: 0 });
}

document.querySelectorAll("[data-view]").forEach((el) => {
  el.addEventListener("click", (e) => {
    e.preventDefault();
    showView(el.dataset.view);
  });
});

function closeMenu() {
  $("sidebar").classList.remove("open");
  $("scrim").classList.add("hidden");
  $("menu-toggle").setAttribute("aria-expanded", "false");
}

$("menu-toggle").addEventListener("click", () => {
  const open = !$("sidebar").classList.contains("open");
  $("sidebar").classList.toggle("open", open);
  $("scrim").classList.toggle("hidden", !open);
  $("menu-toggle").setAttribute("aria-expanded", String(open));
});
$("scrim").addEventListener("click", closeMenu);

/* ---------- Theme ---------- */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("theme-toggle").querySelector("use").setAttribute("href", theme === "dark" ? "#i-sun" : "#i-moon");
}

$("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next);
  try { localStorage.setItem("theme", next); } catch { /* storage unavailable */ }
});

try { applyTheme(localStorage.getItem("theme") || "dark"); } catch { applyTheme("dark"); }

/* ---------- Sound ---------- */

// Labels that count as a safe password and earn applause.
const SAFE_LABELS = ["Strong", "Very Strong"];

const music = $("bg-music");
music.volume = 0.25;
const clickSound = new Audio("/static/audio/click.mp3");
clickSound.volume = 0.5;
const clapSound = new Audio("/static/audio/clapping.mp3");
clapSound.volume = 0.8;

let soundOn = true;
let interacted = false; // browsers block audio until the first click or key press
try { soundOn = localStorage.getItem("sound") !== "off"; } catch { /* storage unavailable */ }

function playEffect(audio) {
  if (!soundOn) return;
  audio.currentTime = 0;
  audio.play().catch(() => {});
}

function updateMusic() {
  if (soundOn && interacted && !document.hidden) music.play().catch(() => {});
  else music.pause();
}

function applySound(on) {
  soundOn = on;
  $("sound-toggle").querySelector("use").setAttribute("href", on ? "#i-sound" : "#i-mute");
  $("sound-toggle").setAttribute("aria-label", on ? "Mute sounds" : "Unmute sounds");
  $("sound-toggle").setAttribute("aria-pressed", String(!on));
  updateMusic();
}

$("sound-toggle").addEventListener("click", () => {
  applySound(!soundOn);
  try { localStorage.setItem("sound", soundOn ? "on" : "off"); } catch { /* storage unavailable */ }
});

for (const type of ["pointerdown", "keydown"]) {
  document.addEventListener(type, () => {
    if (interacted) return;
    interacted = true;
    updateMusic();
  });
}
document.addEventListener("visibilitychange", updateMusic);

document.addEventListener("click", (e) => {
  if (e.target.closest("button, a, input[type=radio], input[type=checkbox]")) playEffect(clickSound);
});

applySound(soundOn);

/* ---------- Step 1: password ---------- */

function setPasswordVisible(show) {
  $("password").type = show ? "text" : "password";
  $("show-password").checked = show;
  $("eye").querySelector("use").setAttribute("href", show ? "#i-eye" : "#i-eye-off");
  $("eye").setAttribute("aria-label", show ? "Hide password" : "Show password");
}

$("eye").addEventListener("click", () => setPasswordVisible($("password").type === "password"));
$("show-password").addEventListener("change", (e) => setPasswordVisible(e.target.checked));

function updateLiveTips() {
  const pw = $("password").value;
  const rules = {
    length: pw.length >= 12,
    case: /[a-z]/.test(pw) && /[A-Z]/.test(pw),
    mix: /\d/.test(pw) && /[^A-Za-z0-9]/.test(pw),
  };
  document.querySelectorAll("#live-tips [data-rule]").forEach((li) => {
    if (li.dataset.rule in rules) li.classList.toggle("ok", rules[li.dataset.rule]);
  });
}
$("password").addEventListener("input", updateLiveTips);

$("password-form").addEventListener("submit", (e) => {
  e.preventDefault();
  showStep("step-questions");
});

/* ---------- Step 2: questions ---------- */

async function loadQuestions() {
  const res = await fetch("/api/questions");
  questions = await res.json();
  $("question-list").replaceChildren(...questions.map((q) => {
    const li = document.createElement("li");
    li.dataset.id = q.id;
    li.innerHTML = `
      <div class="question-text"></div>
      <div class="yes-no">
        <label><input type="radio" name="${q.id}" value="yes"> Yes</label>
        <label><input type="radio" name="${q.id}" value="no"> No</label>
      </div>`;
    li.querySelector(".question-text").textContent = q.text;
    li.addEventListener("change", () => li.classList.remove("missing"));
    return li;
  }));
}

$("back").addEventListener("click", () => showStep("step-password"));

$("questions-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);

  // Validate manually so every unanswered question is highlighted at once.
  const missing = questions.filter((q) => !form.get(q.id));
  document.querySelectorAll("#question-list li").forEach((li) => {
    li.classList.toggle("missing", missing.some((q) => q.id === li.dataset.id));
  });
  $("questions-error").classList.toggle("hidden", missing.length === 0);
  if (missing.length) {
    document.querySelector("#question-list li.missing").scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }

  const answers = {};
  for (const q of questions) answers[q.id] = form.get(q.id) === "yes";

  const submit = e.target.querySelector("[type=submit]");
  submit.disabled = true;
  try {
    const res = await fetch("/api/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: $("password").value, answers }),
    });
    if (!res.ok) throw new Error();
    renderResult(await res.json());
  } catch {
    alert("Something went wrong. Please try again.");
  } finally {
    submit.disabled = false;
  }
});

/* ---------- Step 3: result ---------- */

function fillList(el, items) {
  el.replaceChildren(...items.map((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    return li;
  }));
}

function renderResult(r) {
  assessmentId = r.id;
  const color = LABEL_COLORS[r.label];
  const f = r.features;

  $("result-label").textContent = r.label;
  $("result-label").style.color = color;
  $("result-summary").textContent = LABEL_SUMMARIES[r.label] ?? "";
  $("crack-time").textContent = r.crack_time_display;

  $("ring-fill").style.stroke = color;
  $("ring-fill").style.color = color;
  $("ring-fill").style.strokeDashoffset = RING_CIRCUMFERENCE;
  $("bar-marker").style.left = "0%";
  animateNumber($("result-score"), r.score);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    $("ring-fill").style.strokeDashoffset = RING_CIRCUMFERENCE * (1 - r.score / 100);
    $("bar-marker").style.left = `${r.score}%`;
  }));

  const types = [f.has_lower, f.has_upper, f.has_digit, f.has_symbol || f.has_other].filter(Boolean).length;
  $("stat-length").textContent = f.length;
  $("stat-types").textContent = `${types}/4`;
  $("stat-patterns").textContent = f.patterns.length ? `${f.patterns.length} detected` : "0 detected";

  $("issues-block").classList.toggle("hidden", r.issues.length === 0);
  fillList($("issues"), r.issues);
  fillList($("tips"), r.tips);
  renderImprovements(r);

  $("ai-block").classList.toggle("hidden", !r.ai_advice_available);
  if (r.ai_advice_available) loadAdvice(r.id);

  document.querySelectorAll("[data-feedback]").forEach((b) => {
    b.disabled = false;
    b.classList.remove("selected");
  });
  $("feedback-thanks").classList.add("hidden");

  showStep("step-result");
  if (SAFE_LABELS.includes(r.label)) playEffect(clapSound);
}

function renderImprovements(r) {
  const steps = r.improvements;
  $("improve-block").classList.toggle("hidden", !steps.length && !r.replace_recommended);
  $("improve-intro").classList.toggle("hidden", !steps.length);
  $("improvements").classList.toggle("hidden", !steps.length);
  $("replace-note").classList.toggle("hidden", !r.replace_recommended);

  let previous = r.score;
  $("improvements").replaceChildren(...steps.map((step) => {
    const li = document.createElement("li");
    const fix = document.createElement("span");
    fix.textContent = step.fix;
    const score = document.createElement("span");
    score.className = "step-score";
    score.textContent = step.score;
    const gain = document.createElement("span");
    gain.className = "gain";
    gain.textContent = step.score > previous ? `+${step.score - previous}` : "";
    previous = step.score;
    li.append(fix, score, gain);
    return li;
  }));
}

$("improve-passphrase").addEventListener("click", () => {
  setGeneratorMode("words");
  showView("generator");
});

function animateNumber(el, target) {
  const start = performance.now();
  const duration = 900;
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    el.textContent = Math.round(target * (1 - Math.pow(1 - t, 3)));
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* ---------- AI advice ---------- */

// Fetched as soon as the result is shown; the rest of the result doesn't wait for it.
async function loadAdvice(id) {
  const box = $("ai-advice");
  box.classList.add("loading");
  box.textContent = "Gemma is thinking…";
  let text;
  try {
    const res = await fetch(`/api/assessments/${id}/advice`, { method: "POST" });
    const data = await res.json();
    text = res.ok ? data.advice : `Could not get advice: ${data.detail}`;
  } catch {
    text = "Could not reach the server.";
  }
  if (id !== assessmentId) return; // the user has started a new check
  box.classList.remove("loading");
  box.textContent = text;
}

/* ---------- Feedback & restart ---------- */

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

function resetChecker() {
  $("password").value = "";
  $("questions-form").reset();
  document.querySelectorAll("#question-list li").forEach((li) => li.classList.remove("missing"));
  $("questions-error").classList.add("hidden");
  setPasswordVisible(false);
  updateLiveTips();
  assessmentId = null;
  showStep("step-password");
}

$("restart").addEventListener("click", () => {
  resetChecker();
  $("password").focus();
});

/* ---------- Password generator ---------- */

const CHARSETS = {
  "gen-lower": "abcdefghijklmnopqrstuvwxyz",
  "gen-upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  "gen-digits": "0123456789",
  "gen-symbols": "!@#$%^&*()-_=+[]{};:,.?/~",
};

// Unbiased random integer in [0, max) using rejection sampling.
function randomInt(max) {
  const limit = Math.floor(0x100000000 / max) * max;
  const buf = new Uint32Array(1);
  do crypto.getRandomValues(buf); while (buf[0] >= limit);
  return buf[0] % max;
}

let generatorMode = "chars";
let passphraseWords = null; // EFF large word list, loaded on first use

function setGeneratorMode(mode) {
  generatorMode = mode;
  document.querySelectorAll("[data-gen-mode]").forEach((b) => {
    const active = b.dataset.genMode === mode;
    b.classList.toggle("selected", active);
    b.setAttribute("aria-pressed", active);
  });
  $("gen-chars-options").classList.toggle("hidden", mode !== "chars");
  $("gen-words-options").classList.toggle("hidden", mode !== "words");
  generatePassword();
}

async function generatePassphrase() {
  if (!passphraseWords) {
    try {
      const res = await fetch("/static/wordlists/eff-large.txt");
      if (!res.ok) throw new Error();
      passphraseWords = (await res.text()).split("\n").filter(Boolean);
    } catch {
      $("gen-output").value = "";
      $("gen-words-bits").textContent = "Could not load the word list.";
      return;
    }
  }
  const count = Number($("gen-words").value);
  const words = Array.from({ length: count }, () => passphraseWords[randomInt(passphraseWords.length)]);
  const capitalize = $("gen-capitalize").checked;
  const formatted = words.map((w) => (capitalize ? w[0].toUpperCase() + w.slice(1) : w));
  let bits = count * Math.log2(passphraseWords.length);
  if ($("gen-number").checked) {
    formatted[randomInt(count)] += randomInt(10);
    bits += Math.log2(10);
  }
  $("gen-output").value = formatted.join("-");
  $("gen-words-bits").textContent = `About ${Math.floor(bits)} bits of randomness.`;
}

function generatePassword() {
  if (generatorMode === "words") {
    generatePassphrase();
    return;
  }
  const sets = Object.keys(CHARSETS).filter((id) => $(id).checked).map((id) => CHARSETS[id]);
  if (!sets.length) {
    $("gen-lower").checked = true;
    sets.push(CHARSETS["gen-lower"]);
  }
  const length = Number($("gen-length").value);
  const all = sets.join("");
  // Guarantee at least one character from each selected set, then shuffle.
  const chars = sets.map((s) => s[randomInt(s.length)]);
  while (chars.length < length) chars.push(all[randomInt(all.length)]);
  for (let i = chars.length - 1; i > 0; i--) {
    const j = randomInt(i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  $("gen-output").value = chars.join("");
}

$("gen-length").addEventListener("input", (e) => {
  $("gen-length-value").textContent = e.target.value;
  generatePassword();
});
Object.keys(CHARSETS).forEach((id) => $(id).addEventListener("change", generatePassword));
$("gen-refresh").addEventListener("click", generatePassword);
document.querySelectorAll("[data-gen-mode]").forEach((b) => {
  b.addEventListener("click", () => setGeneratorMode(b.dataset.genMode));
});
$("gen-words").addEventListener("input", (e) => {
  $("gen-words-value").textContent = e.target.value;
  generatePassword();
});
["gen-capitalize", "gen-number"].forEach((id) => $(id).addEventListener("change", generatePassword));

$("gen-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("gen-output").value);
    $("gen-copy").querySelector("use").setAttribute("href", "#i-check");
    setTimeout(() => $("gen-copy").querySelector("use").setAttribute("href", "#i-copy"), 1200);
  } catch {
    $("gen-output").select();
  }
});

$("gen-check").addEventListener("click", () => {
  const generated = $("gen-output").value;
  resetChecker();
  $("password").value = generated;
  updateLiveTips();
  showView("checker");
  $("password").focus();
});

/* ---------- Init ---------- */

showView("home");
showStep("step-password");
loadQuestions();
