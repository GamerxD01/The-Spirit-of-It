// Dadi's Voice Archive: tiny vanilla front end. No CDN, no fonts from the internet: works fully offline.
const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (t) => { t = Math.max(0, Math.floor(t || 0)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };
const STATUS = { queued: "waiting…", transcribing: "listening to her…", remembering: "Gemma is remembering…", transcribed: "words saved, not translated", error: "something went wrong", done: "" };

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}
const post = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

let poll = null;
function stopPoll() { if (poll) clearTimeout(poll); poll = null; }

// ------------------------------------------------------------------ status pill
async function loadStatus() {
  const el = $("#status");
  try {
    const s = await api("/api/status");
    el.className = "pill " + (s.llm_ok ? "ok" : "warn");
    el.textContent = s.llm_ok ? `● offline-ready · ${s.model} · whisper ${s.whisper}` : `● whisper ${s.whisper} · Gemma offline`;
    el.title = s.llm_ok ? `Ollama at ${s.ollama}. Nothing is sent to the cloud.` : s.error;
  } catch { el.textContent = "server not running"; el.className = "pill warn"; }
}

// ------------------------------------------------------------------ altar
async function altar() {
  const elders = await api("/api/elders");
  view.innerHTML = `
    <h1>The ofrenda</h1>
    <p class="lede">Record the people who carry your family's stories, in their own voice and their own language.
      Whisper writes down every word, Gemma translates and remembers. All of it runs on this computer.</p>
    <div class="altar">
      ${elders.map((e) => `
        <a class="frame" href="#/elder/${e.id}">
          <div class="mono">${esc([...e.name][0] || "?")}</div>
          <div class="name">${esc(e.name)}</div>
          <div class="rel">${esc(e.relation)}${e.years ? " · " + esc(e.years) : ""}</div>
          <div class="count">${e.story_count} ${e.story_count === 1 ? "story" : "stories"} · ${Math.round(e.seconds / 60)} min of their voice</div>
          <span class="diya lamp"><i></i></span>
        </a>`).join("")}
      <div class="frame add" id="add" tabindex="0" role="button">+ Add someone to remember</div>
    </div>
    <div id="form"></div>`;
  $("#add").onclick = () => {
    $("#form").innerHTML = `
      <div class="panel" style="margin-top:30px;max-width:520px">
        <h2>Who carries the stories?</h2>
        <label for="n">Name</label><input id="n" placeholder="Dadi, Nani, Bade Papa…" autofocus>
        <label for="r">Relation</label><input id="r" placeholder="Father's mother">
        <label for="y">Years</label><input id="y" placeholder="1941 – ">
        <label for="o">A line about them</label><textarea id="o" rows="2" placeholder="Grew up in a village near Faizabad, sang while grinding wheat"></textarea>
        <p><button class="btn" id="save">Place on the ofrenda</button></p>
      </div>`;
    $("#save").onclick = async () => {
      const name = $("#n").value.trim();
      if (!name) return $("#n").focus();
      const { id } = await post("/api/elders", { name, relation: $("#r").value, years: $("#y").value, note: $("#o").value });
      location.hash = `#/elder/${id}`;
    };
  };
}

// ------------------------------------------------------------------ elder page
async function elder(id) {
  const e = await api(`/api/elders/${id}`);
  view.innerHTML = `
    <a class="back" href="#/">← back to the ofrenda</a>
    <h1>${esc(e.name)}</h1>
    <p class="lede">${esc(e.relation)}${e.years ? " · " + esc(e.years) : ""}${e.note ? "<br>" + esc(e.note) : ""}</p>
    <div class="grid2">
      <section class="panel">
        <h2>Record a story</h2>
        <div class="rec">
          <button class="recbtn" id="rec" aria-label="Start recording"></button>
          <div><div class="timer" id="timer">0:00</div><div class="small muted" id="recmsg">Tap to start. Let them talk, don't interrupt.</div></div>
        </div>
        <label for="lang">Language they speak</label>
        <select id="lang">
          <option value="hi">Hindi / Awadhi / Bhojpuri</option><option value="">Detect automatically</option>
          <option value="ur">Urdu</option><option value="pa">Punjabi</option><option value="bn">Bengali</option>
          <option value="mr">Marathi</option><option value="ta">Tamil</option><option value="en">English</option><option value="es">Spanish</option>
        </select>
        <label for="file">…or add an old recording (WhatsApp voice note, mp3, m4a)</label>
        <input type="file" id="file" accept="audio/*,.opus,.ogg,.m4a">
        <p class="hint">Good first questions: What did your mother cook on festivals? What songs did you sing at weddings? What was the village like before the road came?</p>
        <p class="err" id="recerr"></p>
      </section>
      <section class="panel">
        <h2>Ask what ${esc(e.name)} remembered</h2>
        <div class="ask"><input id="q" placeholder="What did she cook for Diwali?"><button class="btn" id="askbtn">Ask</button></div>
        <p class="hint">Answers come only from her recordings, with her voice at the exact moment. If she never said it, it says so.</p>
        <div id="answer"></div>
      </section>
    </div>
    <section class="panel">
      <h2>Stories</h2>
      <ul class="stories" id="stories"></ul>
      <p style="margin-top:18px"><button class="btn danger" id="del">Remove ${esc(e.name)} and all recordings</button></p>
    </section>`;
  renderStories(e.stories);
  setupRecorder(id);
  $("#askbtn").onclick = () => doAsk(id);
  $("#q").onkeydown = (ev) => { if (ev.key === "Enter") doAsk(id); };
  $("#del").onclick = async () => {
    if (!window.confirm(`Delete ${e.name} and every recording? This cannot be undone.`)) return;
    await api(`/api/elders/${id}`, { method: "DELETE" });
    location.hash = "#/";
  };
  const tick = async () => {
    const fresh = await api(`/api/elders/${id}`).catch(() => null);
    if (!fresh || !location.hash.startsWith(`#/elder/${id}`)) return;
    renderStories(fresh.stories);
    if (fresh.stories.some((s) => ["queued", "transcribing", "remembering"].includes(s.status))) poll = setTimeout(tick, 2500);
  };
  if (e.stories.some((s) => ["queued", "transcribing", "remembering"].includes(s.status))) poll = setTimeout(tick, 2500);
  view._refresh = () => { stopPoll(); poll = setTimeout(tick, 800); };
}

function renderStories(stories) {
  const ul = $("#stories");
  if (!ul) return;
  if (!stories.length) { ul.innerHTML = `<li class="empty">No stories yet. The first one is the hardest to ask for.</li>`; return; }
  ul.innerHTML = stories.map((s) => {
    const t = s.tags || {};
    const chips = ["people", "places", "foods", "songs"].flatMap((k) => (t[k] || []).slice(0, 3).map((x) => `<span class="chip cat-${k}">${esc(x)}</span>`)).join("");
    return `<li><a href="#/story/${s.id}">
      <div class="t">${esc(s.title || "A new story")} <span class="chip s-${s.status}">${STATUS[s.status] ?? s.status}</span></div>
      <div class="small muted">${fmt(s.duration)} · ${esc(s.created_at.slice(0, 10))}${t.era ? " · " + esc(t.era) : ""}</div>
      ${s.summary ? `<div class="muted">${esc(s.summary)}</div>` : ""}
      <div>${chips}</div></a></li>`;
  }).join("");
}

async function upload(elderId, blob, filename) {
  const fd = new FormData();
  fd.append("audio", blob, filename);
  fd.append("language", $("#lang").value);
  $("#recmsg").textContent = "Saving…";
  try {
    await api(`/api/elders/${elderId}/stories`, { method: "POST", body: fd });
    $("#recmsg").textContent = "Saved. Whisper is listening to it now.";
    view._refresh && view._refresh();
  } catch (err) { $("#recerr").textContent = err.message; }
}

function setupRecorder(elderId) {
  let rec = null, chunks = [], started = 0, timer = null;
  const btn = $("#rec");
  btn.onclick = async () => {
    $("#recerr").textContent = "";
    if (rec && rec.state === "recording") { rec.stop(); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { $("#recerr").textContent = "Microphone permission was denied."; return; }
    chunks = [];
    rec = new MediaRecorder(stream);
    rec.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data);
    rec.onstop = () => {
      clearInterval(timer); btn.classList.remove("on"); stream.getTracks().forEach((t) => t.stop());
      const type = rec.mimeType || "audio/webm";
      upload(elderId, new Blob(chunks, { type }), type.includes("ogg") ? "story.ogg" : type.includes("mp4") ? "story.m4a" : "story.webm");
    };
    rec.start(1000);
    started = Date.now(); btn.classList.add("on"); btn.setAttribute("aria-label", "Stop recording");
    $("#recmsg").textContent = "Recording. Tap again when they finish.";
    timer = setInterval(() => ($("#timer").textContent = fmt((Date.now() - started) / 1000)), 250);
  };
  $("#file").onchange = (ev) => { const f = ev.target.files[0]; if (f) upload(elderId, f, f.name); };
}

// ---- grounded answers with her real voice
const player = new Audio();
let stopAt = null, activeBtn = null;
player.ontimeupdate = () => { if (stopAt && player.currentTime >= stopAt) { player.pause(); } };
player.onpause = () => { activeBtn && activeBtn.classList.remove("on"); activeBtn && (activeBtn.textContent = "▶"); };

async function playClip(btn, storyId, start, end) {
  if (activeBtn === btn && !player.paused) { player.pause(); return; }
  const st = await api(`/api/stories/${storyId}`);
  const src = `/audio/${st.audio_file}`;
  if (!player.src.endsWith(src)) player.src = src;
  activeBtn && activeBtn.classList.remove("on");
  activeBtn = btn; btn.classList.add("on"); btn.textContent = "❚❚";
  const go = () => { player.currentTime = Math.max(0, start - 0.3); stopAt = end + 0.5; player.play(); };
  player.readyState >= 1 ? go() : player.addEventListener("loadedmetadata", go, { once: true });
}

async function doAsk(elderId) {
  const q = $("#q").value.trim();
  if (!q) return;
  const box = $("#answer");
  box.innerHTML = `<p class="muted small">Searching her recordings…</p>`;
  try {
    const r = await post(`/api/elders/${elderId}/ask`, { question: q });
    box.innerHTML = `<div class="answer">${esc(r.answer)}</div>` + r.sources.map((s) => `
      <div class="source">
        <button class="play" data-s="${s.story_id}" data-a="${s.start}" data-b="${s.end}" aria-label="Play this moment">▶</button>
        <div><span class="small muted">[${s.n}] ${esc(s.title)} · ${fmt(s.start)}</span><br>${esc(s.text)}
          ${s.translation ? `<span class="en">${esc(s.translation)}</span>` : ""}</div>
      </div>`).join("");
    box.querySelectorAll(".play").forEach((b) => (b.onclick = () => playClip(b, +b.dataset.s, +b.dataset.a, +b.dataset.b)));
  } catch (err) { box.innerHTML = `<p class="err">${esc(err.message)}</p>`; }
}

// ------------------------------------------------------------------ story page
async function story(id) {
  const s = await api(`/api/stories/${id}`);
  const t = s.tags || {};
  const cats = { people: "People", places: "Places", foods: "Foods", songs: "Songs" };
  const busy = ["queued", "transcribing", "remembering"].includes(s.status);
  view.innerHTML = `
    <a class="back" href="#/elder/${s.elder_id}">← ${esc(s.elder_name)}</a>
    <input class="title-edit" id="title" value="${esc(s.title || "A new story")}" aria-label="Story title">
    <p class="muted small">${esc(s.elder_name)} · ${fmt(s.duration)} · ${esc(s.language || "")} · ${esc(s.created_at.slice(0, 10))}${t.era ? " · " + esc(t.era) : ""}
      ${STATUS[s.status] ? ` · <span class="chip s-${s.status}">${STATUS[s.status]}</span>` : ""}</p>
    ${s.error ? `<p class="err">${esc(s.error)}</p>` : ""}
    <audio id="aud" controls src="/audio/${esc(s.audio_file)}"></audio>
    ${t.keepsake ? `<div class="keepsake">“${esc(t.keepsake)}”</div>` : ""}
    ${s.summary ? `<p>${esc(s.summary)}</p>` : ""}
    <p>${Object.entries(cats).flatMap(([k, label]) => (t[k] || []).map((x) => `<span class="chip cat-${k}" title="${label}">${esc(x)}</span>`)).join("")}</p>
    <section class="panel">
      <h2>Her words</h2>
      <div class="lines" id="lines">${s.segments.length ? s.segments.map((g) => `
        <p data-a="${g.start}" data-b="${g.end}"><span class="ts">${fmt(g.start)}</span>${esc(g.text)}
          ${g.translation ? `<span class="en">${esc(g.translation)}</span>` : ""}</p>`).join("") : `<p class="empty">${busy ? "Whisper is still listening…" : "No words found."}</p>`}</div>
    </section>
    <p>
      ${["transcribed", "error", "done"].includes(s.status) ? `<button class="btn ghost" id="again">Remember again with Gemma</button>` : ""}
      <button class="btn danger" id="delst">Delete this story</button>
    </p>`;
  const aud = $("#aud");
  const lines = [...view.querySelectorAll("#lines p[data-a]")];
  lines.forEach((p) => (p.onclick = () => { aud.currentTime = +p.dataset.a; aud.play(); }));
  aud.ontimeupdate = () => {
    const now = aud.currentTime;
    lines.forEach((p) => p.classList.toggle("now", now >= +p.dataset.a && now < +p.dataset.b));
  };
  $("#title").onchange = () => api(`/api/stories/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: $("#title").value }) });
  $("#again") && ($("#again").onclick = async () => { await post(`/api/stories/${id}/remember`, {}); route(); });
  $("#delst").onclick = async () => {
    if (!window.confirm("Delete this recording forever?")) return;
    await api(`/api/stories/${id}`, { method: "DELETE" });
    location.hash = `#/elder/${s.elder_id}`;
  };
  if (busy) poll = setTimeout(() => location.hash === `#/story/${id}` && route(), 3000);
}

// ------------------------------------------------------------------ router
async function route(scroll = false) {
  stopPoll();
  const [, kind, id] = location.hash.split("/");
  try {
    if (kind === "elder") await elder(+id);
    else if (kind === "story") await story(+id);
    else await altar();
  } catch (err) { view.innerHTML = `<p class="err">${esc(err.message)}</p><a href="#/">Home</a>`; }
  if (scroll) window.scrollTo(0, 0);
}
window.addEventListener("hashchange", () => route(true));
loadStatus();
setInterval(loadStatus, 15000);
route();
