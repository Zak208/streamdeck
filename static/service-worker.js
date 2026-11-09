// StreamDesk Service Worker for PWA installation & caching
const CACHE_NAME = 'streamdesk-v2.17.2';
const ASSETS_TO_CACHE = [
  '/',
  '/static/css/tokens.css',
  '/static/css/style.css',
  '/static/js/streamdeck.js',
  '/static/js/monitors.js',
  '/static/js/phone-settings.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-maskable-192.png',
  '/static/icons/icon-maskable-512.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/discord.svg',
  '/static/icons/spotify.svg',
  '/static/icons/obs.svg',
  '/static/icons/steam.svg',
  '/static/icons/chrome.svg',
  '/static/icons/gear.svg',
  '/static/icons/mic.svg',
  '/static/icons/mic_off.svg',
  '/static/icons/mute.svg',
  '/static/icons/power.svg',
  '/static/icons/volume_up.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch((err) => {
        console.log('Cache addAll warning:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// How long to wait for the PC before showing the saved copy: with the PC off or its address changed, the app still opens.
const NETWORK_WAIT_MS = 2500;

self.addEventListener('fetch', (event) => {
  // Let WebSocket and API requests go directly to network
  const url = event.request.url;
  if (url.includes('/api/') || url.includes('/ws') || event.request.method !== 'GET') {
    return;
  }

  event.respondWith((async () => {
    // The saved copy ignores the ?v= of the address, so the files saved at install are found.
    const saved = () => caches.match(event.request, { ignoreSearch: true });
    const fromNetwork = fetch(event.request, { cache: 'no-cache' }).then((response) => {
      // The PIN in the address is a secret that expires: never keep it. Only whole, good answers are saved.
      if (response && response.status === 200 && !new URL(url).searchParams.has('pin')) {
        const responseClone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
      }
      return response;
    });
    const deadline = new Promise((resolve) => setTimeout(() => resolve(null), NETWORK_WAIT_MS));
    try {
      // no-cache makes the browser ask the PC whether the file changed, so an update reaches phones that had cached the old page.
      const first = await Promise.race([fromNetwork, deadline]);
      if (first) return first;
      return (await saved()) || (await fromNetwork);
    } catch (err) {
      // Offline: the saved copy, and for a page load the saved start page, so the app still opens.
      const copy = await saved();
      if (copy) return copy;
      return event.request.mode === 'navigate' ? (await caches.match('/', { ignoreSearch: true })) || Response.error() : Response.error();
    }
  })());
});
