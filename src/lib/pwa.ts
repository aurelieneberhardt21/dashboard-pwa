import { registerSW } from 'virtual:pwa-register'

const unregisterAllServiceWorkers = async () => {
  if (!('serviceWorker' in navigator)) {
    return
  }

  const registrations = await navigator.serviceWorker.getRegistrations()
  await Promise.all(registrations.map((registration) => registration.unregister()))
}

export const registerAppServiceWorker = () => {
  if (import.meta.env.DEV) {
    void unregisterAllServiceWorkers()
    return () => {}
  }

  return registerSW({
    immediate: true,
    onOfflineReady() {
      console.info('PWA offline cache ready')
    },
    onRegisterError(error) {
      console.error('SW registration error', error)
    },
  })
}
