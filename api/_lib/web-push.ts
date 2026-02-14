import * as webpush from 'web-push'
import { requiredEnv } from './env'

const vapidSubject = requiredEnv('VAPID_SUBJECT')
const vapidPublicKey = requiredEnv('VAPID_PUBLIC_KEY')
const vapidPrivateKey = requiredEnv('VAPID_PRIVATE_KEY')

webpush.setVapidDetails(vapidSubject, vapidPublicKey, vapidPrivateKey)

export type ServerPushSubscription = {
  endpoint: string
  p256dh: string
  auth: string
}

export type PushPayload = {
  title: string
  body: string
  url: string
  tag?: string
}

export const sendWebPush = async (subscription: ServerPushSubscription, payload: PushPayload) => {
  await webpush.sendNotification(
    {
      endpoint: subscription.endpoint,
      keys: {
        p256dh: subscription.p256dh,
        auth: subscription.auth,
      },
    },
    JSON.stringify({
      title: payload.title,
      body: payload.body,
      url: payload.url,
      tag: payload.tag,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
    }),
  )
}
