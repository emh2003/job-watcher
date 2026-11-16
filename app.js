/* Job Watcher site. Shared by index.html, browse.html and market.html.
   Loads data/history.csv and data/status.json and does every calculation here,
   in the browser. */

// ---------- small helpers ----------
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
const fmt = (n) => Number(n).toLocaleString("en-US");
const plural = (n, word) => `${fmt(n)} ${word}${n === 1 ? "" : "s"}`;
const daysBetween = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
const addDays = (d, n) => new Date(Date.parse(d) + n * 86400000).toISOString().slice(0, 10);
const shortDate = (d) => new Date(d + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

function parseCSV(text) {
  const rows = []; let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else quoted = false; }
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const header = rows.shift() || [];
  return rows.filter((r) => r.length === header.length).map((r) => Object.fromEntries(header.map((h, i) => [h, r[i]])));
}

async function loadData() {
  const get = async (path) => { const r = await fetch(path, { cache: "no-store" }); if (!r.ok) throw new Error(path + " " + r.status); return r; };
  const [h, s] = await Promise.all([get("data/history.csv").then((r) => r.text()), get("data/status.json").then((r) => r.json())]);
  const history = parseCSV(h).map((r) => ({ ...r, in_role: r.in_role === "true", first_run: r.first_run === "true" }));
  return { history, status: s };
}

// The date of the last run, taken from the history file alone.
function lastRunDate(history) {
  let last = "";
  for (const r of history) { if (r.last_seen > last) last = r.last_seen; if (r.removed_date > last) last = r.removed_date; }
  return last;
}

// ---------- shared page frame ----------
function frame(page) {
  const tabs = [["index.html", "Today"], ["browse.html", "Browse"], ["market.html", "Market"]];
  document.body.insertAdjacentHTML("afterbegin", `
    <nav class="nav"><div class="nav-in">
      <a class="brand" href="index.html">Job Watcher</a>
      <span class="offline" role="status">Offline: showing saved data</span>
      ${tabs.map(([href, name]) => `<a class="tab" href="${href}"${href === page ? ' aria-current="page"' : ""}>${name}</a>`).join("")}
    </div></nav>`);
  const setOffline = () => document.body.classList.toggle("is-offline", !navigator.onLine);
  addEventListener("online", setOffline); addEventListener("offline", setOffline); setOffline();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
}

// ---------- shortlist (kept in the browser) ----------
const Shortlist = {
  key: "job-watcher-shortlist",
  all() { try { return new Set(JSON.parse(localStorage.getItem(this.key) || "[]")); } catch { return new Set(); } },
  toggle(id) { const s = this.all(); s.has(id) ? s.delete(id) : s.add(id); try { localStorage.setItem(this.key, JSON.stringify([...s])); } catch {} return s.has(id); },
};

function postingItem(r, opts = {}) {
  const starred = opts.starred && opts.starred.has(r.posting_id);
  const star = opts.starred ? `<button class="star" data-id="${esc(r.posting_id)}" aria-pressed="${starred}" aria-label="Save ${esc(r.title)} to shortlist" title="Save to shortlist">★</button>` : "";
  const meta = [r.employer, r.location, r.department].filter(Boolean).map(esc).join(" · ");
  return `<li>${star}<div class="what"><span class="title">${esc(r.title)}</span>${r.in_role ? '<span class="pill">my role</span>' : ""}
    <div class="meta">${meta}${opts.extra ? " · " + esc(opts.extra(r)) : ""}</div></div>
    <a class="apply" href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">${opts.linkText || "Apply"} ↗</a></li>`;
}

// ---------- charts (plain SVG) ----------
function niceMax(v) {  // a round axis top that splits into four whole-number steps
  if (v <= 4) return 4;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 4, 6, 8, 10, 12, 16, 20]) if (v <= m * p && (m * p) % 4 === 0) return m * p;
  return 20 * p;
}

function attachTips(el) {
  const tip = document.createElement("div"); tip.className = "tip"; el.appendChild(tip);
  el.addEventListener("pointermove", (e) => {
    const g = e.target.closest("[data-tip]");
    if (!g) { tip.style.display = "none"; return; }
    const box = el.getBoundingClientRect();
    tip.textContent = g.dataset.tip; tip.style.display = "block";
    tip.style.left = Math.min(Math.max(e.clientX - box.left, 60), box.width - 60) + "px"; tip.style.top = e.clientY - box.top + "px";
  });
  el.addEventListener("pointerleave", () => (tip.style.display = "none"));
}

function dataTable(el, head, rows) {
  el.insertAdjacentHTML("beforeend", `<details class="data"><summary>Show the numbers</summary><table><thead><tr>${head.map((h, i) => `<th${i ? ' class="num"' : ""}>${esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i ? ' class="num"' : ""}>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></details>`);
}

// Vertical bars: one value per label (days, or buckets).
function columnChart(el, { labels, values, color = "var(--series-1)", unit = "posting", head = ["Day", "Postings"], label = "" }) {
  el.classList.add("chart");
  if (!labels.length) { el.innerHTML = '<p class="empty">Nothing to chart yet.</p>'; return; }
  const W = 720, H = 220, m = { l: 44, r: 8, t: 10, b: 26 };
  const max = niceMax(Math.max(...values, 1)), iw = W - m.l - m.r, ih = H - m.t - m.b;
  const step = iw / labels.length, bw = Math.max(2, Math.min(34, step - 2));
  const y = (v) => m.t + ih - (v / max) * ih;
  const every = Math.ceil(labels.length / 9);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">`;
  for (let i = 0; i <= 4; i++) { const v = (max / 4) * i; s += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${fmt(v)}</text>`; }
  labels.forEach((lab, i) => {
    const x = m.l + i * step + (step - bw) / 2, v = values[i], h = (v / max) * ih, r = Math.min(4, h);
    s += `<g data-tip="${esc(lab)}: ${esc(plural(v, unit))}"><rect class="hit" x="${m.l + i * step}" y="${m.t}" width="${step}" height="${ih}"/>`;
    if (v > 0) s += `<path class="bar" fill="${color}" d="M${x},${y(0)} V${y(v) + r} Q${x},${y(v)} ${x + r},${y(v)} H${x + bw - r} Q${x + bw},${y(v)} ${x + bw},${y(v) + r} V${y(0)} Z"/>`;
    s += `</g>`;
    if (i % every === 0) s += `<text x="${m.l + i * step + step / 2}" y="${H - 8}" text-anchor="middle">${esc(lab)}</text>`;
  });
  el.innerHTML = s + "</svg>";
  attachTips(el); dataTable(el, head, labels.map((l, i) => [l, fmt(values[i])]));
}

// Horizontal bars: ranked categories, each bar labeled with its value.
function barChart(el, { labels, values, color = "var(--series-1)", unit = "posting", head = ["Name", "Postings"], label = "" }) {
  el.classList.add("chart");
  if (!labels.length) { el.innerHTML = '<p class="empty">Nothing to chart yet.</p>'; return; }
  const W = 720, rowH = 26, lw = 200, pad = 56, H = labels.length * rowH + 6;
  const max = Math.max(...values, 1), iw = W - lw - pad;
  const cut = (t) => (t.length > 30 ? t.slice(0, 29) + "…" : t);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">`;
  labels.forEach((lab, i) => {
    const yy = i * rowH + 4, w = Math.max(values[i] > 0 ? 2 : 0, (values[i] / max) * iw), r = Math.min(4, w);
    s += `<g data-tip="${esc(lab)}: ${esc(plural(values[i], unit))}"><rect class="hit" x="0" y="${yy - 3}" width="${W}" height="${rowH}"/>
      <text x="${lw - 8}" y="${yy + 14}" text-anchor="end">${esc(cut(lab))}</text>
      <path class="bar" fill="${color}" d="M${lw},${yy} H${lw + w - r} Q${lw + w},${yy} ${lw + w},${yy + r} V${yy + 20 - r} Q${lw + w},${yy + 20} ${lw + w - r},${yy + 20} H${lw} Z"/>
      <text class="val" x="${lw + w + 6}" y="${yy + 14}">${fmt(values[i])}</text></g>`;
  });
  el.innerHTML = s + "</svg>";
  attachTips(el); dataTable(el, head, labels.map((l, i) => [l, fmt(values[i])]));
}

const countBy = (rows, key) => { const m = new Map(); for (const r of rows) { const k = typeof key === "function" ? key(r) : r[key]; m.set(k, (m.get(k) || 0) + 1); } return m; };
const topN = (map, n) => [...map.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]))).slice(0, n);
const median = (xs) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b), mid = s.length >> 1; return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2; };

// ---------- Today page ----------
function todayPage({ history, status }) {
  const date = status.run_time.slice(0, 10);
  const when = new Date(status.run_time);
  $("#last-run").textContent = `Last run: ${when.toLocaleString("en-US", { dateStyle: "long", timeStyle: "short" })} (${status.run_time.replace("T", " ").replace("Z", " UTC")})`;
  const tiles = [[status.days_with_success, "days with a successful run"], [status.open, "open postings"], [status.new_today, "new today"], [status.removed_today, "removed today"]];
  $("#tiles").innerHTML = tiles.map(([n, l]) => `<div class="tile"><b>${fmt(n)}</b><span>${l}</span></div>`).join("");

  const okCount = status.sources.filter((s) => s.ok).length;
  $("#sources-head").textContent = `Sources: ${okCount} of ${status.sources.length} answered`;
  $("#sources").innerHTML = status.sources.map((s) => `<li><span class="${s.ok ? "ok" : "fail"}">${s.ok ? "✓ OK" : "✗ Failed"}</span><span>${esc(s.name)}</span><span class="muted">${s.ok ? fmt(s.count) : "0"}</span></li>`).join("");

  const roleFirst = (a, b) => b.in_role - a.in_role || a.employer.localeCompare(b.employer) || a.title.localeCompare(b.title);
  const lists = [
    ["#new", history.filter((r) => r.first_seen === date && !r.first_run).sort(roleFirst), "New postings", "Apply"],
    ["#removed", history.filter((r) => r.removed_date === date).sort(roleFirst), "Removed postings", "Posting"],
  ];
  for (const [sel, rows, name, linkText] of lists) {
    const role = rows.filter((r) => r.in_role).length, LIMIT = 150;
    $(sel + "-head").textContent = `${name} in the latest run (${fmt(rows.length)}${rows.length ? `, ${fmt(role)} in my role` : ""})`;
    $(sel).innerHTML = rows.length
      ? `<ul class="posts">${rows.slice(0, LIMIT).map((r) => postingItem(r, { linkText })).join("")}</ul>` + (rows.length > LIMIT ? `<p class="muted small">Showing the first ${LIMIT} of ${fmt(rows.length)}. The daily GitHub Issue and data/history.csv hold the full list.</p>` : "")
      : `<p class="empty">${status.days_with_success <= 1 && sel === "#new" ? "This is the first run, so every posting was already open. New postings show up from the second day." : "None in the latest run."}</p>`;
  }
}

// ---------- Browse page ----------
function browsePage({ history }) {
  const last = lastRunDate(history);
  const open = history.filter((r) => r.status === "open").map((r) => ({ ...r, days: daysBetween(r.first_seen, last) }));
  const state = { role: true, employer: "", location: "", days: "", q: "", sort: "new", saved: false, shown: 200 };
  const fill = (sel, map, all) => { $(sel).innerHTML = `<option value="">${all}</option>` + topN(map, 500).sort((a, b) => a[0].localeCompare(b[0])).map(([k, n]) => `<option value="${esc(k)}">${esc(k)} (${fmt(n)})</option>`).join(""); };
  const DAYS = { "0-3": [0, 3], "4-7": [4, 7], "8-14": [8, 14], "15+": [15, Infinity] };

  function options() {  // employer and location lists follow the role switch
    const base = open.filter((r) => !state.role || r.in_role);
    const keep = (sel) => $(sel).value;
    const e = keep("#f-employer"), l = keep("#f-location");
    fill("#f-employer", countBy(base, "employer"), "All employers");
    fill("#f-location", countBy(base.filter((r) => r.location), "location"), "All locations");
    $("#f-employer").value = e; $("#f-location").value = l;
    state.employer = $("#f-employer").value; state.location = $("#f-location").value;
  }

  function render() {
    const starred = Shortlist.all(), q = state.q.trim().toLowerCase();
    const rows = open.filter((r) =>
      (!state.role || r.in_role) && (!state.employer || r.employer === state.employer) && (!state.location || r.location === state.location) &&
      (!state.days || (r.days >= DAYS[state.days][0] && r.days <= DAYS[state.days][1])) &&
      (!q || r.title.toLowerCase().includes(q)) && (!state.saved || starred.has(r.posting_id)));
    rows.sort((a, b) => (state.sort === "new" ? b.first_seen.localeCompare(a.first_seen) : a.first_seen.localeCompare(b.first_seen)) || a.employer.localeCompare(b.employer) || a.title.localeCompare(b.title));
    $("#count").textContent = `${plural(rows.length, "open posting")}${state.role ? " in my role" : ""} · ${starred.size} on the shortlist`;
    const extra = (r) => `${r.first_run ? "open at least " : "open "}${plural(r.days, "day")} · first seen ${shortDate(r.first_seen)}`;
    $("#list").innerHTML = rows.length
      ? `<ul class="posts">${rows.slice(0, state.shown).map((r) => postingItem(r, { starred, extra })).join("")}</ul>` + (rows.length > state.shown ? `<p style="text-align:center"><button class="btn" id="more">Show more (${fmt(rows.length - state.shown)} left)</button></p>` : "")
      : '<p class="empty">No open postings match these filters.</p>';
  }

  const set = (k, v) => { state[k] = v; state.shown = 200; render(); };
  $("#f-employer").onchange = (e) => set("employer", e.target.value);
  $("#f-location").onchange = (e) => set("location", e.target.value);
  $("#f-days").onchange = (e) => set("days", e.target.value);
  $("#f-sort").onchange = (e) => set("sort", e.target.value);
  $("#f-q").oninput = (e) => set("q", e.target.value);
  $("#f-saved").onchange = (e) => set("saved", e.target.checked);
  for (const b of document.querySelectorAll("#f-role button")) b.onclick = () => {
    state.role = b.dataset.role === "role";
    document.querySelectorAll("#f-role button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    options(); set("shown", 200);
  };
  $("#list").addEventListener("click", (e) => {
    const star = e.target.closest(".star");
    if (star) { star.setAttribute("aria-pressed", String(Shortlist.toggle(star.dataset.id))); state.saved ? render() : ($("#count").textContent = $("#count").textContent.replace(/· \d+ on/, `· ${Shortlist.all().size} on`)); }
    if (e.target.id === "more") { state.shown += 200; render(); }
  });
  options(); render();
}

// ---------- Market page: every number comes from history.csv ----------
function marketNumbers(history) {
  const last = lastRunDate(history);
  const first = history.reduce((m, r) => (r.first_seen < m ? r.first_seen : m), last);
  const days = []; for (let d = first; d && d <= last; d = addDays(d, 1)) days.push(d);
  const fresh = history.filter((r) => !r.first_run);
  const perDay = (rows, key) => { const m = countBy(rows, key); return days.map((d) => m.get(d) || 0); };
  const removed = history.filter((r) => r.status === "removed" && r.removed_date);
  const open = history.filter((r) => r.status === "open");
  const daysOpen = removed.filter((r) => !r.first_run).map((r) => daysBetween(r.first_seen, r.removed_date));
  const cohort = fresh.filter((r) => daysBetween(r.first_seen, last) >= 7);
  const quick = cohort.filter((r) => r.status === "removed" && daysBetween(r.first_seen, r.removed_date) <= 7);
  return {
    last, days,
    newAll: perDay(fresh, "first_seen"), newRole: perDay(fresh.filter((r) => r.in_role), "first_seen"),
    removedPerDay: perDay(removed, "removed_date"),
    openTotal: open.length, employers: topN(countBy(open, "employer"), 100),
    daysOpen, medianDaysOpen: median(daysOpen),
    cohort: cohort.length, quick: quick.length, share: cohort.length ? quick.length / cohort.length : null,
    locations: topN(countBy(open.filter((r) => r.location), "location"), 12),
  };
}

function marketPage({ history }) {
  const n = marketNumbers(history);
  window.marketData = n;  // handy for checking the page against history.csv
  const labels = n.days.map(shortDate), sum = (xs) => xs.reduce((a, b) => a + b, 0);
  const peak = (vals) => { const m = Math.max(...vals, 0); return { m, day: m ? labels[vals.indexOf(m)] : "" }; };
  const sec = (id, heading, text) => { $(`#${id} h2`).textContent = heading; $(`#${id} p`).innerHTML = text; };
  $("#asof").textContent = `Computed in your browser from data/history.csv · ${fmt(history.length)} postings tracked · last run ${n.last || "none yet"} · ${plural(n.days.length, "day")} of history`;

  // 1. New postings per day
  const tAll = sum(n.newAll), tRole = sum(n.newRole), pk = peak(n.newAll), nd = Math.max(n.days.length - 1, 1);
  sec("s1", tAll ? `Employers post about ${fmt(Math.round(tAll / nd))} new jobs a day; ${tRole ? `about ${(tRole / nd).toFixed(1)} a day are in my role` : "none so far in my role"}` : "No new postings have appeared since the first run yet",
    `A posting is new on the day the watcher first sees it. Postings that were already open on a source's first run are left out, because their real start date is unknown. Since the first run there have been <b>${fmt(tAll)}</b> new postings, <b>${fmt(tRole)}</b> of them in my role (financial analyst / FP&amp;A)${pk.m ? `. The busiest day was ${pk.day} with ${fmt(pk.m)}` : ""}.`);
  columnChart($("#c1a"), { labels, values: n.newAll, label: "New postings per day, all postings" });
  columnChart($("#c1b"), { labels, values: n.newRole, color: "var(--series-2)", label: "New postings per day, my role" });

  // 2. Removed postings per day
  const tRem = sum(n.removedPerDay), pr = peak(n.removedPerDay);
  sec("s2", tRem ? `${fmt(tRem)} postings have come down, about ${fmt(Math.round(tRem / nd))} a day` : "No postings have been removed yet",
    `A posting is removed on the first day its employer's board answers without listing it. A day when a board fails to answer removes nothing.${pr.m ? ` Most removals in one day: ${fmt(pr.m)} on ${pr.day}.` : ""}`);
  columnChart($("#c2"), { labels, values: n.removedPerDay, label: "Removed postings per day" });

  // 3. Open postings per employer
  const e0 = n.employers[0];
  sec("s3", e0 ? `${e0[0]} has the most open postings: ${fmt(e0[1])} of ${fmt(n.openTotal)}` : "No open postings yet",
    `Open postings at each watched employer as of the last run (${n.last}). This counts every posting on the board, not only those in my role.`);
  barChart($("#c3"), { labels: n.employers.map((e) => e[0]), values: n.employers.map((e) => e[1]), head: ["Employer", "Open postings"], label: "Open postings per employer" });

  // 4. Days open
  const md = n.medianDaysOpen;
  sec("s4", md === null ? "No posting has opened and closed while being watched yet" : `A posting that comes down has typically been open ${plural(md, "day")}`,
    md === null ? "Days open is the removed date minus the first-seen date, for removed postings that were not already open on the first run. None qualify yet; this fills in as the history grows."
      : `Days open is the removed date minus the first-seen date, for the <b>${fmt(n.daysOpen.length)}</b> removed postings that were first seen after the first run. The median is <b>${md} days</b>. Early on this number runs low, because only short-lived postings have had time to open and close.`);
  const maxD = Math.max(...n.daysOpen, 0), hist = Array.from({ length: maxD + 1 }, () => 0); n.daysOpen.forEach((d) => hist[d]++);
  columnChart($("#c4"), { labels: n.daysOpen.length ? hist.map((_, i) => String(i)) : [], values: hist, head: ["Days open", "Postings"], label: "Removed postings by days open" });
  if (n.daysOpen.length) $("#c4").insertAdjacentHTML("afterbegin", '<p class="chart-title">Removed postings by number of days open</p>');

  // 5. Share removed within seven days
  const pct = n.share === null ? null : Math.round(n.share * 100);
  sec("s5", pct === null ? "Too early to say how many postings close within a week" : `${pct}% of new postings are gone within seven days`,
    pct === null ? "This needs postings first seen at least seven days before the last run (and not already open on the first run). None are old enough yet."
      : `Of the <b>${fmt(n.cohort)}</b> postings first seen at least seven days before the last run (leaving out first-run postings), <b>${fmt(n.quick)}</b> were removed within seven days of first being seen. That is ${pct}%.`);
  barChart($("#c5"), n.cohort ? { labels: ["Removed within 7 days", "Still open after 7 days"], values: [n.quick, n.cohort - n.quick], head: ["Group", "Postings"], label: "Postings removed within seven days" } : { labels: [], values: [] });

  // 6. Top locations
  const l0 = n.locations[0];
  sec("s6", l0 ? `${l0[0]} is the top location with ${fmt(l0[1])} open postings` : "No open postings yet",
    `The ${n.locations.length} most common locations among open postings, using each employer's own wording for the location${l0 && n.openTotal ? `. The top one holds ${Math.round((l0[1] / n.openTotal) * 100)}% of all open postings` : ""}.`);
  barChart($("#c6"), { labels: n.locations.map((e) => e[0]), values: n.locations.map((e) => e[1]), head: ["Location", "Open postings"], label: "Top locations among open postings" });
}

// ---------- start ----------
async function start(page) {
  frame(page + ".html");
  try {
    const data = await loadData();
    ({ index: todayPage, browse: browsePage, market: marketPage })[page](data);
  } catch (err) {
    console.error(err);
    $("main").insertAdjacentHTML("beforeend", `<div class="card"><p class="empty">The data files could not be loaded. If the pipeline has not finished its first run yet, check back after it has.</p></div>`);
  }
}
start(document.body.dataset.page);
