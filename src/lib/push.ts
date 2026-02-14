import { env } from './env'
import { supabase } from './supabase'
import type { PushSubscriptionPayload } from '../types'

const toUint8Array = (base64String: string) => {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const normalized = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(normalized)
  return Uint8Array.from(rawData, (char) => char.charCodeAt(0))
}

const subscriptionToPayload = (subscription: PushSubscription): PushSubscriptionPayload => {
  const json = subscription.toJSON()

  return {
    endpoint: subscription.endpoint,
    p256dh: json.keys?.p256dh ?? '',
    auth: json.keys?.auth ?? '',
    user_agent: navigator.userAgent,
  }
}

export const canUsePush = () => {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

export const requestAndSubscribePush = async (userId: string) => {
  if (!canUsePush()) {
    throw new Error('Push non supporté sur ce navigateur.')
  }

  if (!env.vapidPublicKey) {
    throw new Error('VITE_VAPID_PUBLIC_KEY est manquant.')
  }

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Permission notifications refusée.')
  }

  const registration = await navigator.serviceWorker.ready
  const current = await registration.pushManager.getSubscription()
  const subscription =
    current ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: toUint8Array(env.vapidPublicKey),
    }))

  const payload = subscriptionToPayload(subscription)
  const { error } = await supabase.from('push_subscriptions').upsert(
    {
      user_id: userId,
      endpoint: payload.endpoint,
      p256dh: payload.p256dh,
      auth: payload.auth,
      user_agent: payload.user_agent,
      updated_at: new Date().toISOString(),
    },
    { onConflict: 'user_id,endpoint' },
  )

  if (error) {
    throw error
  }

  return payload
}

export const unsubscribePush = async (userId: string) => {
  if (!('serviceWorker' in navigator)) {
    return
  }

  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.getSubscription()

  let endpoint: string | null = null
  if (subscription) {
    endpoint = subscription.endpoint
    await subscription.unsubscribe()
  }

  if (endpoint) {
    await supabase.from('push_subscriptions').delete().eq('user_id', userId).eq('endpoint', endpoint)
  }
}

export const hasPushSubscription = async () => {
  if (!('serviceWorker' in navigator)) {
    return false
  }
  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.getSubscription()
  return Boolean(subscription)
}
