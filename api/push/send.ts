import type { VercelRequest, VercelResponse } from '@vercel/node'
import { optionalEnv } from '../_lib/env'
import { sendWebPush } from '../_lib/web-push'

type Body = {
  subscription?: {
    endpoint: string
    p256dh: string
    auth: string
  }
  payload?: {
    title: string
    body: string
    url: string
    tag?: string
  }
}

const isAuthorized = (request: VercelRequest) => {
  const internalSecret = optionalEnv('INTERNAL_API_SECRET')
  if (!internalSecret) {
    return true
  }

  const bearer = request.headers.authorization?.replace('Bearer ', '')
  const xApiKey = request.headers['x-api-key']

  return bearer === internalSecret || xApiKey === internalSecret
}

export default async function handler(request: VercelRequest, response: VercelResponse) {
  if (request.method !== 'POST') {
    response.status(405).json({ error: 'Method not allowed' })
    return
  }

  if (!isAuthorized(request)) {
    response.status(401).json({ error: 'Unauthorized' })
    return
  }

  const body = request.body as Body

  if (!body.subscription || !body.payload) {
    response.status(400).json({ error: 'Missing subscription or payload' })
    return
  }

  try {
    await sendWebPush(body.subscription, body.payload)
    response.status(200).json({ ok: true })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Push failed'
    response.status(500).json({ error: message })
  }
}
