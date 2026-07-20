// Custom "add to home screen" modal. iOS Safari has no beforeinstallprompt
// API, so this is a hand-built instructional modal (matches the pattern of
// other sites' install prompts) rather than relying on a native browser hook.
(function () {
  const STEPS = {
    ios: [
      "פתחי את האתר דרך <strong>Safari</strong> (לא Chrome או אפליקציה אחרת).",
      "הקישי על כפתור <strong>השיתוף</strong> (הריבוע עם החץ כלפי מעלה) בתחתית המסך.",
      "גללי מטה ובחרי <strong>&quot;הוסף למסך הבית&quot;</strong>.",
      "הקישי <strong>&quot;הוסף&quot;</strong> למעלה — האייקון יופיע במסך הבית כמו אפליקציה רגילה.",
    ],
    android: [
      "פתחי את האתר דרך <strong>Chrome</strong>.",
      "הקישי על תפריט שלוש הנקודות (⋮) בפינה הימנית העליונה.",
      "בחרי <strong>&quot;התקנת אפליקציה&quot;</strong> או <strong>&quot;הוספה למסך הבית&quot;</strong>.",
      "אשרי — האייקון יופיע במסך הבית ויפתח במסך מלא, בלי סרגל דפדפן.",
    ],
  };

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    );
  }

  function detectPlatform() {
    const ua = navigator.userAgent || "";
    if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
    return "android";
  }

  function buildModal() {
    const overlay = document.createElement("div");
    overlay.className = "install-overlay hidden";
    overlay.id = "installOverlay";

    const platform = detectPlatform();

    overlay.innerHTML = `
      <div class="install-modal" role="dialog" aria-modal="true" aria-label="התקנת האפליקציה">
        <div class="install-modal-header">
          <h2>📲 התקנת האפליקציה</h2>
          <button class="install-close" id="installCloseBtn" aria-label="סגירה">×</button>
        </div>
        <p class="install-desc">
          הוסיפי את עדכון החדשות למסך הבית לגישה מהירה בלחיצה אחת — במסך מלא, בלי סרגל דפדפן, בדיוק כמו אפליקציה רגילה.
        </p>
        <div class="install-tabs">
          <button class="install-tab-btn" data-platform="ios" type="button">iPhone (Safari)</button>
          <button class="install-tab-btn" data-platform="android" type="button">אנדרואיד (Chrome)</button>
        </div>
        <div class="install-steps" id="installSteps"></div>
        <button class="primary-btn" id="installGotItBtn" type="button">✓ הבנתי</button>
      </div>
    `;
    document.body.appendChild(overlay);

    const reopenBtn = document.createElement("button");
    reopenBtn.className = "icon-btn install-reopen";
    reopenBtn.id = "installReopenBtn";
    reopenBtn.type = "button";
    reopenBtn.textContent = "📲 התקנת אפליקציה";
    document.body.appendChild(reopenBtn);

    function renderSteps(p) {
      const stepsEl = overlay.querySelector("#installSteps");
      stepsEl.innerHTML = STEPS[p]
        .map(
          (text, i) => `
          <div class="install-step">
            <div class="install-step-num">${i + 1}</div>
            <div class="install-step-text">${text}</div>
          </div>`
        )
        .join("");
      overlay.querySelectorAll(".install-tab-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.platform === p);
      });
    }

    renderSteps(platform);

    overlay.querySelectorAll(".install-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => renderSteps(btn.dataset.platform));
    });

    function show() {
      overlay.classList.remove("hidden");
    }
    function hide() {
      overlay.classList.add("hidden");
      NewsDigestStorage.setInstallDismissed();
    }

    overlay.querySelector("#installCloseBtn").addEventListener("click", hide);
    overlay.querySelector("#installGotItBtn").addEventListener("click", hide);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) hide();
    });
    reopenBtn.addEventListener("click", show);

    return { show };
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (isStandalone()) return; // already installed, nothing to do
    const modal = buildModal();
    if (!NewsDigestStorage.isInstallDismissed()) {
      setTimeout(modal.show, 400);
    }
  });
})();
