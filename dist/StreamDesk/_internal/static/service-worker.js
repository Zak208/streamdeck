// StreamDesk Service Worker for PWA installation & caching
const CACHE_NAME = 'streamdesk-v2.1';
const ASSETS_TO_CACHE = [
  '/',
  '/static/css/style.css',
  '/static/js/streamdeck.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/discord.svg',
  '/static/icons/spotify.svg',
  '/static/icons/obs.svg',
  '/static/icons/steam.svg',
  '/static/icons/chrome.svg',
  '/static/icons/gear.svg'
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

self.addEventListener('fetch', (event) => {
  // Let WebSocket and API requests go directly to network
  const url = event.request.url;
  if (url.includes('/api/') || url.includes('/ws') || event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});

