(function () {
  const mainEl = document.getElementById("main");

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

  function headlineItem(h) {
    const time = formatTime(h.published_at);
    return `
      <li class="headline-item">
        <a href="${h.url}" target="_blank" rel="noopener">${h.title}</a>
        <span class="headline-source">${h.source_label_he}${time ? " · " + time : ""}</span>
      </li>`;
  }

  function heroHeadline(h) {
    const time = formatTime(h.published_at);
    const imageHtml = h.image_url
      ? `<img class="hero-image" src="${h.image_url}" alt="" loading="lazy"
           onerror="this.closest('.hero-headline').classList.add('no-image'); this.remove();" />`
      : "";
    return `
      <a class="hero-headline${h.image_url ? "" : " no-image"}" href="${h.url}" target="_blank" rel="noopener">
        ${imageHtml}
        <div class="hero-headline-text">
          <span class="hero-title">${h.title}</span>
          <span class="headline-source">${h.source_label_he}${time ? " · " + time : ""}</span>
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

  const VISIBLE_EXTRA = 1; // number of extra headlines shown before "see more"

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

  function alwaysOnCard({ title, cssClass, data }) {
    if (!data || !data.headlines || !data.headlines.length) return "";
    const [lead, ...rest] = data.headlines;
    return `
      <div class="card ${cssClass || ""}">
        <div class="card-title-row"><h3>${title}</h3></div>
        ${heroHeadline(lead)}
        <p class="card-summary">${data.summary_he || ""}</p>
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

  function render(data) {
    const dateLine = document.getElementById("dateLine");
    if (dateLine) dateLine.textContent = formatHebrewDate(data.date);

    const sections = [];

    if (data.degraded) {
      sections.push(`<div class="demo-banner">⚠️ זהו תוכן לדוגמה. העדכון האמיתי היומי עדיין לא הופעל.</div>`);
    }

    sections.push(`<div class="section">
      ${alwaysOnCard({ title: "📰 הכותרות המרכזיות", data: data.top_general })}
    </div>`);

    sections.push(`<div class="section">
      ${alwaysOnCard({ title: "🛡️ ביטחון ומלחמה", cssClass: "security", data: data.security_war })}
    </div>`);

    if (data.subjects && data.subjects.length) {
      sections.push(`<div class="section">
        <div class="section-title">✨ התחומים שאת עוקבת אחריהם</div>
        ${data.subjects.map(subjectCard).join("")}
      </div>`);
    }

    mainEl.innerHTML = sections.join("");
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
