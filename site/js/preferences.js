(function () {
  // NOTE: mailto: recipient is intentionally a plain visible address (not
  // obfuscated) — this repo is public and mailto links expose the address
  // in the page source anyway; the only real downside is extra spam risk,
  // which is an accepted, low-stakes tradeoff for a personal family tool.
  const RECIPIENT_EMAIL = "benefron@gmail.com";

  const listEl = document.getElementById("prefList");
  const customListEl = document.getElementById("customList");
  const customInput = document.getElementById("customSubjectInput");
  const addCustomBtn = document.getElementById("addCustomBtn");
  const sendBtn = document.getElementById("sendUpdateBtn");
  const confirmationEl = document.getElementById("confirmationNote");

  let catalog = [];
  let originalPrefs = null; // as loaded, for diffing
  let checkedState = {}; // key -> bool, for catalog items
  let customSubjects = []; // [{key, label_he}] newly added this session
  let removedCustomKeys = []; // custom subjects that existed before and got unchecked/removed

  function slugify(label) {
    // stable-ish key from Hebrew label: hash the text since Hebrew has no
    // meaningful ASCII slug: 8 hex chars is enough to avoid collisions here.
    let hash = 0;
    for (let i = 0; i < label.length; i++) {
      hash = (hash * 31 + label.charCodeAt(i)) >>> 0;
    }
    return "custom_" + hash.toString(16).slice(0, 8);
  }

  function renderChecklist() {
    listEl.innerHTML = catalog
      .map((topic) => {
        const checked = checkedState[topic.key] ? "checked" : "";
        return `
          <li class="pref-item">
            <label>
              <input type="checkbox" data-key="${topic.key}" data-label="${topic.label_he}" ${checked} />
              ${topic.label_he}
            </label>
          </li>`;
      })
      .join("");

    listEl.querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.addEventListener("change", () => {
        checkedState[cb.dataset.key] = cb.checked;
      });
    });
  }

  function renderCustomChips() {
    customListEl.innerHTML = customSubjects
      .map(
        (s) => `
        <li class="custom-chip" data-key="${s.key}">
          ${s.label_he}
          <button type="button" data-remove-key="${s.key}" aria-label="הסרה">✕</button>
        </li>`
      )
      .join("");

    customListEl.querySelectorAll("[data-remove-key]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.removeKey;
        const wasOriginal = (originalPrefs?.subjects || []).some(
          (s) => s.key === key && s.source === "user_added"
        );
        if (wasOriginal) removedCustomKeys.push(key);
        customSubjects = customSubjects.filter((s) => s.key !== key);
        renderCustomChips();
      });
    });
  }

  function addCustomSubject() {
    const label = (customInput.value || "").trim();
    if (!label) return;
    const key = slugify(label);
    if (customSubjects.some((s) => s.key === key)) {
      customInput.value = "";
      return;
    }
    customSubjects.push({ key, label_he: label });
    customInput.value = "";
    renderCustomChips();
  }

  function buildDiff() {
    const enableKeys = [];
    const disableKeys = [];
    const originalEnabled = {};
    (originalPrefs?.subjects || []).forEach((s) => {
      if (s.source !== "user_added") originalEnabled[s.key] = s.enabled;
    });
    Object.keys(checkedState).forEach((key) => {
      const now = checkedState[key];
      const before = originalEnabled[key];
      if (before === undefined) return;
      if (now && !before) enableKeys.push(key);
      if (!now && before) disableKeys.push(key);
    });

    const likes = NewsDigestStorage.getLikes();
    const liked = Object.keys(likes).filter((k) => likes[k] === "like").slice(0, 20);
    const disliked = Object.keys(likes).filter((k) => likes[k] === "dislike").slice(0, 20);

    return {
      schema_version: 1,
      generated_at: new Date().toISOString(),
      changes: {
        add_subjects: customSubjects,
        remove_subject_keys: removedCustomKeys,
        enable_subject_keys: enableKeys,
        disable_subject_keys: disableKeys,
      },
      feedback: {
        liked_subject_keys: liked,
        disliked_subject_keys: disliked,
      },
    };
  }

  function keyToLabel(key) {
    const inCatalog = catalog.find((c) => c.key === key);
    if (inCatalog) return inCatalog.label_he;
    const inCustom = customSubjects.find((c) => c.key === key);
    if (inCustom) return inCustom.label_he;
    const inOriginal = (originalPrefs?.subjects || []).find((s) => s.key === key);
    return inOriginal ? inOriginal.label_he : key;
  }

  function buildMailto(diff) {
    const dateStr = new Date().toISOString().slice(0, 10);
    const subject = `[NewsDigestUpdate] עדכון העדפות – ${dateStr}`;

    const lines = ["עדכון להעדפות שלי:"];
    diff.changes.add_subjects.forEach((s) => lines.push(`✅ הוספתי: ${s.label_he}`));
    diff.changes.remove_subject_keys.forEach((k) => lines.push(`🗑️ הסרתי: ${keyToLabel(k)}`));
    diff.changes.enable_subject_keys.forEach((k) => lines.push(`🔔 הפעלתי: ${keyToLabel(k)}`));
    diff.changes.disable_subject_keys.forEach((k) => lines.push(`🔕 כיביתי: ${keyToLabel(k)}`));
    diff.feedback.liked_subject_keys.forEach((k) => lines.push(`👍 אהבתי כותרות על: ${keyToLabel(k)}`));
    diff.feedback.disliked_subject_keys.forEach((k) => lines.push(`👎 לא אהבתי כותרות על: ${keyToLabel(k)}`));

    if (lines.length === 1) lines.push("(אין שינויים מיוחדים, רק בדיקה 🙂)");

    const body = `${lines.join("\n")}\n\n\`\`\`json\n${JSON.stringify(diff)}\n\`\`\`\n`;

    return `mailto:${RECIPIENT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }

  function handleSend() {
    const diff = buildDiff();
    const href = buildMailto(diff);
    window.location.href = href;
    confirmationEl.classList.add("visible");
  }

  Promise.all([
    fetch("data/topic_catalog.json").then((r) => r.json()),
    fetch("data/preferences.json").then((r) => r.json()),
  ])
    .then(([catalogData, prefsData]) => {
      catalog = catalogData;
      originalPrefs = prefsData;

      catalog.forEach((topic) => {
        const found = (prefsData.subjects || []).find((s) => s.key === topic.key);
        checkedState[topic.key] = found ? !!found.enabled : false;
      });

      customSubjects = (prefsData.subjects || [])
        .filter((s) => s.source === "user_added" && s.enabled)
        .map((s) => ({ key: s.key, label_he: s.label_he }));

      renderChecklist();
      renderCustomChips();
    })
    .catch(() => {
      listEl.innerHTML = `<li class="error-state">לא הצלחנו לטעון את רשימת הנושאים.</li>`;
    });

  addCustomBtn.addEventListener("click", addCustomSubject);
  customInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addCustomSubject();
    }
  });
  sendBtn.addEventListener("click", handleSend);
})();
