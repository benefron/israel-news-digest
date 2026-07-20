if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {
      // offline caching is a nice-to-have, never block the page on it
    });
  });
}
