/**
 * abgehakt v2 — Service Worker
 * Enables PWA offline support and notification scheduling.
 */
const CACHE_NAME = 'abgehakt-v2-2';
const ASSETS = [
    '/',
    '/index.html',
    '/style.css',
    '/app.js',
    '/manifest.json',
    '/icon-192.png',
    '/icon-512.png',
];

// ── Install ─────────────────────────────────────────────────

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        })
    );
    self.skipWaiting();
});

// ── Activate ────────────────────────────────────────────────

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((k) => k !== CACHE_NAME)
                    .map((k) => caches.delete(k))
            );
        })
    );
    self.clients.claim();
});

// ── Fetch ───────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
    // Only handle GET; let API calls pass through
    if (event.request.method !== 'GET') return;
    if (event.request.url.includes('/api/')) return;

    event.respondWith(
        caches.match(event.request).then((cached) => {
            // Return cached, then update in background
            const fetchPromise = fetch(event.request)
                .then((response) => {
                    if (response.ok) {
                        const clone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, clone);
                        });
                    }
                    return response;
                })
                .catch(() => cached);

            return cached || fetchPromise;
        })
    );
});

// ── Notification Click ──────────────────────────────────────

self.addEventListener('notificationclick', (event) => {
    const targetUrl = event.notification.data?.url || '/';
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if ('navigate' in client && 'focus' in client) {
                    return client.navigate(targetUrl).then(() => client.focus());
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
