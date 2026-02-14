/// <reference lib="webworker" />

import { clientsClaim } from 'workbox-core'
import { precacheAndRoute, cleanupOutdatedCaches, createHandlerBoundToURL } from 'workbox-precaching'
import { registerRoute, NavigationRoute } from 'workbox-routing'
import { CacheFirst, StaleWhileRevalidate } from 'workbox-strategies'
import { ExpirationPlugin } from 'workbox-expiration'

declare let self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<unknown>
}

clientsClaim()
self.skipWaiting()
cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)

registerRoute(
  new NavigationRoute(createHandlerBoundToURL('/index.html')),
)

registerRoute(
  ({ request }) => request.destination === 'style' || request.destination === 'script' || request.destination === 'worker',
  new StaleWhileRevalidate({
    cacheName: 'fg-static-assets',
  }),
)

registerRoute(
  ({ request }) => request.destination === 'image',
  new CacheFirst({
    cacheName: 'fg-images',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 80,
        maxAgeSeconds: 60 * 60 * 24 * 7,
      }),
    ],
  }),
)

type PushPayload = {
  title?: string
  body?: string
  icon?: string
  badge?: string
  tag?: string
  url?: string
}

self.addEventListener('push', (event) => {
  const payload = (() => {
    try {
      return event.data?.json() as PushPayload
    } catch {
      return { body: event.data?.text() }
    }
  })()

  const title = payload.title || 'Rappel de tâche'
  const options: NotificationOptions = {
    body: payload.body || 'Une tâche arrive maintenant.',
    icon: payload.icon || '/icons/icon-192.png',
    badge: payload.badge || '/icons/icon-192.png',
    tag: payload.tag || 'fg-task-reminder',
    data: {
      url: payload.url || '/?tab=today',
    },
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = event.notification.data?.url || '/?tab=today'

  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((windows) => {
        for (const client of windows) {
          const windowClient = client as WindowClient
          if ('focus' in windowClient) {
            if (windowClient.url.includes(self.location.origin)) {
              return windowClient.focus().then(() => windowClient.navigate(target))
            }
          }
        }
        return self.clients.openWindow(target)
      }),
  )
})

export {}
