/* Briefly service worker.
 *
 * Two jobs, and no more than that:
 *   1. keep the app shell so it opens instantly from the home screen;
 *   2. keep the last news it fetched, so a story read on the underground is
 *      still there — while the app itself says, on screen, that what you are
 *      looking at is the last copy rather than the current one.
 *
 * Data is network-first: a news app must never quietly prefer a stale story.
 */
const VERSION = "briefly-v1";
// Audio lives in its own cache so it can be trimmed without dropping the shell.
const AUDIO = "briefly-audio-v1";
const AUDIO_KEEP = 2;
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSION)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== VERSION && key !== AUDIO)
            .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // The app has no third-party dependencies at all — nothing to pass through.
  if (url.origin !== self.location.origin) return;

  if (url.pathname.includes("/media/")) {
    event.respondWith(audio(request));
    return;
  }

  const isData = url.pathname.includes("/api/");

  if (isData) {
    // Network first: today's news beats yesterday's, always.
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(VERSION).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Shell: cache first, refreshed in the background.
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(VERSION).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});


/* Audio, kept for the journey home but never allowed to pile up.
 *
 * A briefing is produced twice a day; keeping every one of them would quietly
 * fill a phone. Two episodes is the whole of what anyone has queued at once,
 * so the cache holds the newest two and drops the rest.
 */
async function audio(request) {
  const cache = await caches.open(AUDIO);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    // A ranged reply is a fragment; only a whole file is worth keeping.
    if (response && response.status === 200) {
      await cache.put(request, response.clone());
      const keys = await cache.keys();
      for (const old of keys.slice(0, Math.max(0, keys.length - AUDIO_KEEP))) {
        await cache.delete(old);
      }
    }
    return response;
  } catch (_) {
    return cached || Response.error();
  }
}
