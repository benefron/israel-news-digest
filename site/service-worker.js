const CACHE_NAME = "newsdigest-shell-v2";
const APP_SHELL = [
  "./",
  "./index.html",
  "./preferences.html",
  "./css/style.css",
  "./js/app.js",
  "./js/preferences.js",
  "./js/storage.js",
  "./js/install-prompt.js",
  "./js/sw-register.js",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
      )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // data/latest.json: always try the network first so she sees today's
  // digest when online; fall back to cache only if offline.
  if (url.pathname.endsWith("/data/latest.json")) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // app shell: cache-first for instant, app-like loads
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
