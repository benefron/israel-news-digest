// Small localStorage helpers. No backend — everything client-side until she
// explicitly sends an update by email (see preferences.js).
const NewsDigestStorage = (() => {
  const KEYS = {
    LIKES: "newsdigest.likes.v1", // { [subjectKey]: "like" | "dislike" }
    INSTALL_DISMISSED: "newsdigest.installDismissed.v1",
  };

  function getLikes() {
    try {
      return JSON.parse(localStorage.getItem(KEYS.LIKES)) || {};
    } catch {
      return {};
    }
  }

  function setLike(subjectKey, value) {
    const likes = getLikes();
    if (value) {
      likes[subjectKey] = value;
    } else {
      delete likes[subjectKey];
    }
    localStorage.setItem(KEYS.LIKES, JSON.stringify(likes));
    return likes;
  }

  function toggleLike(subjectKey, value) {
    const likes = getLikes();
    const next = likes[subjectKey] === value ? null : value;
    return setLike(subjectKey, next);
  }

  function isInstallDismissed() {
    return localStorage.getItem(KEYS.INSTALL_DISMISSED) === "1";
  }

  function setInstallDismissed() {
    localStorage.setItem(KEYS.INSTALL_DISMISSED, "1");
  }

  return { getLikes, setLike, toggleLike, isInstallDismissed, setInstallDismissed };
})();
