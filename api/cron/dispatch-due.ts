import type { VercelRequest, VercelResponse } from '@vercel/node'
import { optionalEnv } from '../_lib/env'
import { supabaseAdmin } from '../_lib/supabase-admin'
import { sendWebPush } from '../_lib/web-push'

type DueTaskRow = {
  id: string
  user_id: string
  title: string
  scheduled_date: string
  due_time: string
  timezone: string
  due_at: string
}

type SubscriptionRow = {
  id: string
  user_id: string
  endpoint: string
  p256dh: string
  auth: string
}

const canRun = (request: VercelRequest) => {
  if (request.headers['x-vercel-cron']) {
    return true
  }

  const secret = optionalEnv('CRON_SECRET')
  if (!secret) {
    return true
  }

  const bearer = request.headers.authorization?.replace('Bearer ', '')
  return bearer === secret
}

const isUnsubscribedError = (error: unknown) => {
  if (!error || typeof error !== 'object') {
    return false
  }

  const statusCode = (error as { statusCode?: number }).statusCode
  return statusCode === 404 || statusCode === 410
}

export default async function handler(request: VercelRequest, response: VercelResponse) {
  if (!canRun(request)) {
    response.status(401).json({ error: 'Unauthorized' })
    return
  }

  try {
    const windowMinutes = Number(request.query.window ?? 5)

    const { data: dueTasks, error: dueError } = await supabaseAdmin.rpc('get_due_tasks', {
      window_minutes: Number.isFinite(windowMinutes) ? windowMinutes : 5,
    })

    if (dueError) {
      throw dueError
    }

    const due = (dueTasks ?? []) as DueTaskRow[]
    if (due.length === 0) {
      response.status(200).json({ ok: true, message: 'No due tasks', sent: 0 })
      return
    }

    const userIds = [...new Set(due.map((task) => task.user_id))]
    const { data: subscriptions, error: subError } = await supabaseAdmin
      .from('push_subscriptions')
      .select('id, user_id, endpoint, p256dh, auth')
      .in('user_id', userIds)

    if (subError) {
      throw subError
    }

    const byUser = new Map<string, SubscriptionRow[]>()
    for (const sub of (subscriptions ?? []) as SubscriptionRow[]) {
      const current = byUser.get(sub.user_id) ?? []
      current.push(sub)
      byUser.set(sub.user_id, current)
    }

    const sentTaskIds = new Set<string>()
    let sentCount = 0

    for (const task of due) {
      const userSubscriptions = byUser.get(task.user_id) ?? []
      if (userSubscriptions.length === 0) {
        continue
      }

      let deliveredToAtLeastOneDevice = false

      for (const sub of userSubscriptions) {
        try {
          await sendWebPush(
            {
              endpoint: sub.endpoint,
              p256dh: sub.p256dh,
              auth: sub.auth,
            },
            {
              title: 'Tâche à lancer maintenant',
              body: `${task.title} • ${task.scheduled_date} ${task.due_time.slice(0, 5)}`,
              url: `/?tab=today&task=${task.id}`,
              tag: `task-${task.id}`,
            },
          )

          deliveredToAtLeastOneDevice = true
          sentCount += 1
        } catch (error) {
          if (isUnsubscribedError(error)) {
            await supabaseAdmin.from('push_subscriptions').delete().eq('id', sub.id)
          }
        }
      }

      if (deliveredToAtLeastOneDevice) {
        sentTaskIds.add(task.id)
      }
    }

    if (sentTaskIds.size > 0) {
      const { error: markError } = await supabaseAdmin.rpc('mark_tasks_notified', {
        task_ids: [...sentTaskIds],
      })

      if (markError) {
        throw markError
      }
    }

    response.status(200).json({
      ok: true,
      scanned: due.length,
      notified_tasks: sentTaskIds.size,
      pushes_sent: sentCount,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Cron dispatch failed'
    response.status(500).json({ error: message })
  }
}
