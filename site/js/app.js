(function () {
  const mainEl = document.getElementById("main");

  // ── Tabs ───────────────────────────────────────────────────────────────────
  const TAB_KEY = "nd_active_tab";
  const tabs = ["israel", "world"];

  function getActiveTab() {
    const stored = localStorage.getItem(TAB_KEY);
    return tabs.includes(stored) ? stored : "israel";
  }

  function setActiveTab(tab) {
    localStorage.setItem(TAB_KEY, tab);
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.hidden = panel.dataset.tab !== tab;
    });
  }

  function buildTabBar() {
    const bar = document.createElement("div");
    bar.className = "tab-bar";
    const active = getActiveTab();
    bar.innerHTML = `
      <button type="button" class="tab-btn${active === "israel" ? " active" : ""}" data-tab="israel">🇮🇱 ישראל</button>
      <button type="button" class="tab-btn${active === "world" ? " active" : ""}" data-tab="world">🌍 עולם</button>`;
    bar.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
    });
    return bar;
  }

  // ── Date / time helpers ────────────────────────────────────────────────────
  function formatHebrewDate(dateStr) {
    try {
      const d = new Date(`${dateStr}T00:00:00`);
      return new Intl.DateTimeFormat("he-IL", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
      }).format(d);
    } catch {
      return dateStr;
    }
  }

  function formatTime(publishedAt) {
    return publishedAt
      ? new Date(publishedAt).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })
      : "";
  }

  // ── Headline renderers ─────────────────────────────────────────────────────
  function sourceLabel(h) {
    return h.source_label || h.source_label_he || h.source_label_en || "";
  }

  function headlineItem(h) {
    const time = formatTime(h.published_at);
    const label = sourceLabel(h);
    return `
      <li class="headline-item">
        <a href="${h.url}" target="_blank" rel="noopener">${h.title}</a>
        <span class="headline-source">${label}${time ? " · " + time : ""}</span>
      </li>`;
  }

  function heroHeadline(h) {
    const time = formatTime(h.published_at);
    const label = sourceLabel(h);
    const imageHtml = h.image_url
      ? `<img class="hero-image" src="${h.image_url}" alt="" loading="lazy"
           onerror="this.closest('.hero-headline').classList.add('no-image'); this.remove();" />`
      : "";
    return `
      <a class="hero-headline${h.image_url ? "" : " no-image"}" href="${h.url}" target="_blank" rel="noopener">
        ${imageHtml}
        <div class="hero-headline-text">
          <span class="hero-title">${h.title}</span>
          <span class="headline-source">${label}${time ? " · " + time : ""}</span>
        </div>
      </a>`;
  }

  function likeButtonsHtml(subjectKey) {
    const likes = NewsDigestStorage.getLikes();
    const state = likes[subjectKey];
    return `
      <div class="like-buttons" data-subject-key="${subjectKey}">
        <button type="button" class="like-btn like-yes ${state === "like" ? "active-like" : ""}" data-value="like">👍 מעניין</button>
        <button type="button" class="like-btn like-no ${state === "dislike" ? "active-dislike" : ""}" data-value="dislike">👎 פחות</button>
      </div>`;
  }

  const VISIBLE_EXTRA = 2; // headlines shown after the hero before "see more"

  function headlineListHtml(headlines) {
    if (!headlines || !headlines.length) return "";
    const visible = headlines.slice(0, VISIBLE_EXTRA);
    const hidden = headlines.slice(VISIBLE_EXTRA);
    const visibleHtml = visible.length
      ? `<ul class="headline-list">${visible.map(headlineItem).join("")}</ul>`
      : "";
    if (!hidden.length) return visibleHtml;
    const hiddenHtml = `<ul class="headline-list headline-list-extra" hidden>${hidden.map(headlineItem).join("")}</ul>`;
    const btn = `<button type="button" class="see-more-btn" data-more="${hidden.length}">עוד ${hidden.length} כותרות ▾</button>`;
    return visibleHtml + hiddenHtml + btn;
  }

  // ── Card builders ──────────────────────────────────────────────────────────
  function alwaysOnCard({ title, cssClass, data, summaryField }) {
    if (!data || !data.headlines || !data.headlines.length) return "";
    const sf = summaryField || "summary_he";
    const [lead, ...rest] = data.headlines;
    return `
      <div class="card ${cssClass || ""}">
        <div class="card-title-row"><h3>${title}</h3></div>
        ${heroHeadline(lead)}
        <p class="card-summary">${data[sf] || ""}</p>
        ${headlineListHtml(rest)}
      </div>`;
  }

  function subjectCard(subject) {
    const [lead, ...rest] = subject.headlines;
    return `
      <div class="card" data-subject-card="${subject.key}">
        <div class="card-title-row">
          <h3>${subject.label_he}</h3>
        </div>
        ${heroHeadline(lead)}
        <p class="card-summary">${subject.summary_he || ""}</p>
        ${headlineListHtml(rest)}
        <div class="card-footer">
          <span class="headline-source">איך זה היה בשבילך?</span>
          ${likeButtonsHtml(subject.key)}
        </div>
      </div>`;
  }

  // ── World tab cards ────────────────────────────────────────────────────────
  const WORLD_CARDS = [
    { key: "israel_jewish", title: "🔯 Israel from the World" },
    { key: "belgium",       title: "🇧🇪 Belgium & Flanders" },
    { key: "europe",        title: "🌍 Europe" },
    { key: "world_top",     title: "📰 World Headlines" },
  ];

  function renderWorld(world) {
    if (!world) {
      return `<div class="empty-state">World & Belgium digest not yet available — check back later.</div>`;
    }
    const sections = [];
    for (const { key, title } of WORLD_CARDS) {
      const sec = world[key];
      if (!sec || !sec.headlines || !sec.headlines.length) continue;
      sections.push(alwaysOnCard({ title, data: sec, summaryField: "summary_en" }));
    }
    return sections.length
      ? `<div class="section">${sections.join("")}</div>`
      : `<div class="empty-state">No world headlines available yet.</div>`;
  }

  // ── Event wiring ───────────────────────────────────────────────────────────
  function wireLikeButtons() {
    document.querySelectorAll(".like-buttons").forEach((wrap) => {
      const key = wrap.dataset.subjectKey;
      wrap.querySelectorAll(".like-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          NewsDigestStorage.toggleLike(key, btn.dataset.value);
          const likes = NewsDigestStorage.getLikes();
          const state = likes[key];
          wrap.querySelector(".like-yes").classList.toggle("active-like", state === "like");
          wrap.querySelector(".like-no").classList.toggle("active-dislike", state === "dislike");
        });
      });
    });
  }

  function wireSeeMoreButtons() {
    document.querySelectorAll(".see-more-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const extra = btn.previousElementSibling;
        if (extra && extra.hasAttribute("hidden")) {
          extra.removeAttribute("hidden");
          btn.textContent = "פחות ▴";
        } else if (extra) {
          extra.setAttribute("hidden", "");
          btn.textContent = `עוד ${btn.dataset.more} כותרות ▾`;
        }
      });
    });
  }

  // ── Main render ────────────────────────────────────────────────────────────
  function render(data) {
    const dateLine = document.getElementById("dateLine");
    if (dateLine) {
      const dateStr = formatHebrewDate(data.date);
      const timeStr = data.generated_at
        ? new Date(data.generated_at).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })
        : "";
      dateLine.textContent = timeStr ? `${dateStr} · עודכן ${timeStr}` : dateStr;
    }

    // Israel tab content
    const israelSections = [];
    if (data.degraded) {
      israelSections.push(`<div class="demo-banner">⚠️ זהו תוכן לדוגמה. העדכון האמיתי היומי עדיין לא הופעל.</div>`);
    }
    israelSections.push(`<div class="section">
      ${alwaysOnCard({ title: "📰 הכותרות המרכזיות", data: data.top_general })}
    </div>`);
    israelSections.push(`<div class="section">
      ${alwaysOnCard({ title: "🛡️ ביטחון ומלחמה", cssClass: "security", data: data.security_war })}
    </div>`);
    if (data.subjects && data.subjects.length) {
      israelSections.push(`<div class="section">
        <div class="section-title">✨ התחומים שאת עוקבת אחריהם</div>
        ${data.subjects.map(subjectCard).join("")}
      </div>`);
    }

    // World tab content
    const worldHtml = renderWorld(data.world);

    // Build full layout: tab bar + two panels
    const tabBar = buildTabBar();
    const israelPanel = document.createElement("div");
    israelPanel.className = "tab-panel";
    israelPanel.dataset.tab = "israel";
    israelPanel.innerHTML = israelSections.join("");

    const worldPanel = document.createElement("div");
    worldPanel.className = "tab-panel";
    worldPanel.dataset.tab = "world";
    worldPanel.innerHTML = worldHtml;

    mainEl.innerHTML = "";
    mainEl.appendChild(tabBar);
    mainEl.appendChild(israelPanel);
    mainEl.appendChild(worldPanel);

    setActiveTab(getActiveTab());
    wireLikeButtons();
    wireSeeMoreButtons();
  }

  function renderError() {
    mainEl.innerHTML = `<div class="error-state">לא הצלחנו לטעון את העדכון של היום. נסי לרענן, או בדקי שוב מאוחר יותר.</div>`;
  }

  mainEl.innerHTML = `<div class="loading-state">טוען את העדכון של היום…</div>`;

  fetch("data/latest.json", { cache: "no-store" })
    .then((res) => {
      if (!res.ok) throw new Error("bad response");
      return res.json();
    })
    .then(render)
    .catch(renderError);
})();
