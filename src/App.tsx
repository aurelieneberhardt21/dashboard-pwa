import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLiveQuery } from 'dexie-react-hooks'
import {
  Bell,
  BellOff,
  BookOpen,
  CalendarDays,
  Cloud,
  CloudOff,
  Download,
  Dumbbell,
  Flame,
  Home,
  LoaderCircle,
  LogIn,
  LogOut,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Star,
  Trash2,
  Trophy,
  Upload,
  Wrench,
} from 'lucide-react'
import { addMonths, endOfWeek, format, getISOWeek, getISOWeekYear, parseISO, startOfWeek, subDays } from 'date-fns'
import { downloadJson, importBackupPayload, serializeBackup } from './lib/backup'
import { buildMonthGrid, compareDateStrings, priorityRank, todayLocalDate, weekFromToday } from './lib/date'
import { db, deleteTaskLocal, getMetaValue, nowIso, putTaskLocal, setMetaValue } from './lib/db'
import { migrateLegacyDataIfNeeded } from './lib/migration'
import { canUsePush, hasPushSubscription, requestAndSubscribePush, unsubscribePush } from './lib/push'
import { registerAppServiceWorker } from './lib/pwa'
import { authRedirectTo, hasSupabaseClientConfig, missingClientEnv, supabase } from './lib/supabase'
import { subscribeTaskChanges, syncNow } from './lib/sync'
import { useOnlineStatus } from './hooks/useOnlineStatus'
import type {
  GymExerciseRecord,
  GymSessionRecord,
  TaskPriority,
  TaskRecord,
  ThesisLogRecord,
} from './types'

type AppTab = 'tasks' | 'calendar' | 'gym' | 'thesis' | 'settings'
type TaskPlan = 'today' | 'week' | 'custom'

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

type NewTaskForm = {
  title: string
  plan: TaskPlan
  weekDate: string
  customDate: string
  priority: TaskPriority
}

type GymStartForm = {
  date: string
  sessionName: string
}

type GymSessionDraft = {
  date: string
  sessionName: string
  durationMinutes: string
  effort: string
  notes: string
  exercises: GymExerciseRecord[]
}

type GymExerciseForm = {
  name: string
  sets: string
  reps: string
  weight: string
}

type ThesisForm = {
  date: string
  wordsWritten: string
  note: string
}

type ReadingArticle = {
  id: string
  title: string
  url: string
}

const APP_TABS: Array<{ key: AppTab; label: string; icon: typeof Home }> = [
  { key: 'tasks', label: 'Plan', icon: Home },
  { key: 'calendar', label: 'Calendrier', icon: CalendarDays },
  { key: 'gym', label: 'Salle', icon: Dumbbell },
  { key: 'thesis', label: 'Thèse', icon: BookOpen },
  { key: 'settings', label: 'Réglages', icon: Wrench },
]

const sortTasks = (a: TaskRecord, b: TaskRecord) => {
  if (a.status !== b.status) {
    return a.status === 'todo' ? -1 : 1
  }

  const priorityDelta = (priorityRank[b.priority] ?? 1) - (priorityRank[a.priority] ?? 1)
  if (priorityDelta !== 0) {
    return priorityDelta
  }

  const dateDelta = compareDateStrings(a.scheduled_date, b.scheduled_date)
  if (dateDelta !== 0) {
    return dateDelta
  }

  const dueDelta = compareDateStrings(a.due_time, b.due_time)
  if (dueDelta !== 0) {
    return dueDelta
  }

  return compareDateStrings(b.updated_at, a.updated_at)
}

const defaultTaskForm = (today: string, weekDate: string): NewTaskForm => ({
  title: '',
  plan: 'today',
  weekDate,
  customDate: today,
  priority: 'normal',
})

const defaultGymStartForm = (today: string): GymStartForm => ({
  date: today,
  sessionName: '',
})

const defaultGymExerciseForm = (): GymExerciseForm => ({
  name: '',
  sets: '',
  reps: '',
  weight: '',
})

const defaultThesisForm = (today: string): ThesisForm => ({
  date: today,
  wordsWritten: '0',
  note: '',
})

const formatStatusDate = (iso: string | null) => {
  if (!iso) {
    return 'Jamais'
  }
  return format(parseISO(iso), 'dd MMM HH:mm')
}

const toPrettyDate = (date: string | null) => {
  if (!date) {
    return 'Sans date'
  }
  try {
    return format(parseISO(`${date}T12:00:00`), 'EEE d MMM')
  } catch {
    return date
  }
}

const priorityStyle: Record<TaskPriority, string> = {
  high: 'bg-rose-100 text-rose-700 border-rose-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  normal: 'bg-slate-100 text-slate-600 border-slate-200',
}

const clampPercentage = (value: number) => Math.min(Math.max(value, 0), 100)

const App = () => {
  const isOnline = useOnlineStatus()
  const today = todayLocalDate()
  const weekDays = useMemo(() => weekFromToday(), [])
  const defaultWeekDate = weekDays.find((day) => day.date >= today)?.date ?? today

  const [sessionUserId, setSessionUserId] = useState<string | null>(null)
  const [sessionEmail, setSessionEmail] = useState<string | null>(null)
  const [emailInput, setEmailInput] = useState('')
  const [authMessage, setAuthMessage] = useState('')

  const [activeTab, setActiveTab] = useState<AppTab>('tasks')
  const [taskForm, setTaskForm] = useState<NewTaskForm>(() => defaultTaskForm(today, defaultWeekDate))
  const [monthCursor, setMonthCursor] = useState(() => new Date())
  const [selectedCalendarDay, setSelectedCalendarDay] = useState(today)

  const [gymStartForm, setGymStartForm] = useState<GymStartForm>(() => defaultGymStartForm(today))
  const [activeGymDraft, setActiveGymDraft] = useState<GymSessionDraft | null>(null)
  const [gymExerciseForm, setGymExerciseForm] = useState<GymExerciseForm>(() => defaultGymExerciseForm())

  const [thesisForm, setThesisForm] = useState<ThesisForm>(() => defaultThesisForm(today))
  const [readingList, setReadingList] = useState<ReadingArticle[]>([])
  const [readingDraftTitle, setReadingDraftTitle] = useState('')
  const [readingDraftUrl, setReadingDraftUrl] = useState('')

  const [syncInProgress, setSyncInProgress] = useState(false)
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null)
  const [syncMessage, setSyncMessage] = useState('')

  const [pushEnabled, setPushEnabled] = useState(false)
  const [pushMessage, setPushMessage] = useState('')

  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [installMessage, setInstallMessage] = useState('')

  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const liveTasks = useLiveQuery(
    async () => {
      if (!sessionUserId) {
        return []
      }
      return db.tasks.where('user_id').equals(sessionUserId).toArray()
    },
    [sessionUserId],
    [],
  )
  const tasks = useMemo(() => (liveTasks ?? []).sort(sortTasks), [liveTasks])

  const liveGymSessions = useLiveQuery(
    async () => {
      if (!sessionUserId) {
        return []
      }
      return db.gymSessions.where('user_id').equals(sessionUserId).toArray()
    },
    [sessionUserId],
    [],
  )
  const gymSessions = useMemo(
    () =>
      [...(liveGymSessions ?? [])].sort((a, b) => {
        if (a.date !== b.date) {
          return b.date.localeCompare(a.date)
        }
        return b.created_at.localeCompare(a.created_at)
      }),
    [liveGymSessions],
  )

  const liveThesisLogs = useLiveQuery(
    async () => {
      if (!sessionUserId) {
        return []
      }
      return db.thesisLogs.where('user_id').equals(sessionUserId).toArray()
    },
    [sessionUserId],
    [],
  )
  const thesisLogs = useMemo(
    () =>
      [...(liveThesisLogs ?? [])].sort((a, b) => {
        if (a.date !== b.date) {
          return b.date.localeCompare(a.date)
        }
        return b.created_at.localeCompare(a.created_at)
      }),
    [liveThesisLogs],
  )

  const queueCount =
    useLiveQuery(
      async () => {
        if (!sessionUserId) {
          return 0
        }
        return db.queue.where('user_id').equals(sessionUserId).count()
      },
      [sessionUserId],
      0,
    ) ?? 0

  useEffect(() => {
    registerAppServiceWorker()
  }, [])

  useEffect(() => {
    const installHandler = (event: Event) => {
      event.preventDefault()
      setInstallPrompt(event as BeforeInstallPromptEvent)
    }

    window.addEventListener('beforeinstallprompt', installHandler)
    return () => window.removeEventListener('beforeinstallprompt', installHandler)
  }, [])

  useEffect(() => {
    if (!hasSupabaseClientConfig) {
      setAuthMessage('Configuration Supabase manquante. Ajoute les variables VITE_* dans .env')
      return
    }

    void supabase.auth.getSession().then(({ data }) => {
      setSessionUserId(data.session?.user.id ?? null)
      setSessionEmail(data.session?.user.email ?? null)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSessionUserId(newSession?.user.id ?? null)
      setSessionEmail(newSession?.user.email ?? null)
    })

    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!sessionUserId) {
      setPushEnabled(false)
      return
    }

    void hasPushSubscription().then((enabled) => {
      setPushEnabled(enabled)
    })
  }, [sessionUserId])

  useEffect(() => {
    if (!sessionUserId) {
      setReadingList([])
      return
    }

    let cancelled = false
    const key = `reading_list_${sessionUserId}`

    void getMetaValue(key).then((raw) => {
      if (cancelled) {
        return
      }
      if (!raw) {
        setReadingList([])
        return
      }

      try {
        const parsed = JSON.parse(raw) as ReadingArticle[]
        const normalized = parsed.filter(
          (item) => item && typeof item.id === 'string' && typeof item.title === 'string' && typeof item.url === 'string',
        )
        setReadingList(normalized)
      } catch {
        setReadingList([])
      }
    })

    return () => {
      cancelled = true
    }
  }, [sessionUserId])

  useEffect(() => {
    if (!sessionUserId) {
      return
    }
    const key = `reading_list_${sessionUserId}`
    void setMetaValue(key, JSON.stringify(readingList))
  }, [readingList, sessionUserId])

  const fireSync = useCallback(
    async (userId: string) => {
      if (!hasSupabaseClientConfig || !isOnline) {
        return
      }

      try {
        setSyncInProgress(true)
        await syncNow(userId)
        setLastSyncAt(nowIso())
        setSyncMessage('')
      } catch {
        setSyncMessage('Sync en attente (réseau ou backend).')
      } finally {
        setSyncInProgress(false)
      }
    },
    [isOnline],
  )

  useEffect(() => {
    if (!sessionUserId) {
      return
    }

    let cancelled = false

    const bootstrap = async () => {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
      const migration = await migrateLegacyDataIfNeeded(sessionUserId, timezone)

      if (cancelled) {
        return
      }

      if (migration.migratedTasks > 0) {
        setSyncMessage(`Migration locale terminée (${migration.migratedTasks} tâches).`)
      }

      await fireSync(sessionUserId)
    }

    void bootstrap()

    const unsubscribe = subscribeTaskChanges(sessionUserId, () => {
      if (!cancelled && isOnline) {
        void fireSync(sessionUserId)
      }
    })

    const interval = window.setInterval(() => {
      if (!cancelled) {
        void fireSync(sessionUserId)
      }
    }, 60_000)

    const onOnline = () => {
      if (!cancelled) {
        void fireSync(sessionUserId)
      }
    }

    window.addEventListener('online', onOnline)

    return () => {
      cancelled = true
      unsubscribe()
      window.clearInterval(interval)
      window.removeEventListener('online', onOnline)
    }
  }, [fireSync, isOnline, sessionUserId])

  const thisWeekStart = format(startOfWeek(new Date(), { weekStartsOn: 1 }), 'yyyy-MM-dd')
  const thisWeekEnd = format(endOfWeek(new Date(), { weekStartsOn: 1 }), 'yyyy-MM-dd')

  const openTasks = useMemo(() => tasks.filter((task) => task.status === 'todo'), [tasks])
  const doneTasks = useMemo(() => tasks.filter((task) => task.status === 'done'), [tasks])

  const overdueTasks = useMemo(
    () => openTasks.filter((task) => Boolean(task.scheduled_date && task.scheduled_date < today)).sort(sortTasks),
    [openTasks, today],
  )

  const todayTasks = useMemo(
    () => openTasks.filter((task) => task.scheduled_date === today).sort(sortTasks),
    [openTasks, today],
  )

  const weekTasks = useMemo(
    () =>
      openTasks
        .filter((task) => Boolean(task.scheduled_date && task.scheduled_date > today && task.scheduled_date <= thisWeekEnd))
        .sort(sortTasks),
    [openTasks, today, thisWeekEnd],
  )

  const laterTasks = useMemo(
    () =>
      openTasks
        .filter((task) => !task.scheduled_date || task.scheduled_date > thisWeekEnd)
        .sort(sortTasks),
    [openTasks, thisWeekEnd],
  )

  const taskSections = useMemo(
    () => [
      { key: 'overdue', title: 'En retard', items: overdueTasks },
      { key: 'today', title: 'Aujourd’hui', items: todayTasks },
      { key: 'week', title: 'Cette semaine', items: weekTasks },
      { key: 'later', title: 'Plus tard', items: laterTasks },
    ],
    [laterTasks, overdueTasks, todayTasks, weekTasks],
  )

  const visibleTaskSections = useMemo(
    () => taskSections.filter((section) => section.items.length > 0),
    [taskSections],
  )

  const completedCountByDate = useMemo(() => {
    const map = new Map<string, number>()
    for (const task of tasks) {
      if (!task.completed_at) {
        continue
      }
      const date = format(parseISO(task.completed_at), 'yyyy-MM-dd')
      map.set(date, (map.get(date) ?? 0) + 1)
    }
    return map
  }, [tasks])

  const calendarGrid = useMemo(() => buildMonthGrid(monthCursor), [monthCursor])

  const calendarDoneTasks = useMemo(
    () =>
      tasks.filter(
        (task) =>
          Boolean(task.completed_at) &&
          format(parseISO(task.completed_at as string), 'yyyy-MM-dd') === selectedCalendarDay,
      ),
    [selectedCalendarDay, tasks],
  )

  const calendarPlannedTasks = useMemo(
    () => tasks.filter((task) => task.scheduled_date === selectedCalendarDay),
    [selectedCalendarDay, tasks],
  )

  const calendarOverdueTasks = useMemo(
    () =>
      tasks.filter(
        (task) => Boolean(task.scheduled_date && task.scheduled_date < selectedCalendarDay && task.status !== 'done'),
      ),
    [selectedCalendarDay, tasks],
  )

  const gymThisWeek = useMemo(
    () => gymSessions.filter((session) => session.date >= thisWeekStart && session.date <= thisWeekEnd),
    [gymSessions, thisWeekEnd, thisWeekStart],
  )

  const gymLast30 = useMemo(() => {
    const border = format(subDays(new Date(), 29), 'yyyy-MM-dd')
    return gymSessions.filter((session) => session.date >= border)
  }, [gymSessions])

  const gymVolumeLast30 = useMemo(
    () =>
      gymLast30.reduce((total, session) => {
        const sessionVolume = session.exercises.reduce((sum, exercise) => {
          const sets = exercise.sets ?? 0
          const reps = exercise.reps ?? 0
          const weight = exercise.weight_kg ?? 0
          return sum + sets * reps * weight
        }, 0)
        return total + sessionVolume
      }, 0),
    [gymLast30],
  )

  const gymCurrentStreak = useMemo(() => {
    const days = new Set(gymSessions.map((session) => session.date))
    let streak = 0

    for (let offset = 0; offset < 365; offset += 1) {
      const day = format(subDays(new Date(), offset), 'yyyy-MM-dd')
      if (days.has(day)) {
        streak += 1
      } else {
        break
      }
    }

    return streak
  }, [gymSessions])

  const thesisToday = useMemo(() => thesisLogs.filter((log) => log.date === today), [thesisLogs, today])

  const thesisThisWeek = useMemo(
    () => thesisLogs.filter((log) => log.date >= thisWeekStart && log.date <= thisWeekEnd),
    [thesisLogs, thisWeekEnd, thisWeekStart],
  )

  const thesisWordsThisWeek = useMemo(
    () => thesisThisWeek.reduce((sum, log) => sum + log.words_written, 0),
    [thesisThisWeek],
  )

  const weeklyReadingArticle = useMemo(() => {
    if (readingList.length === 0) {
      return null
    }

    const seed = getISOWeekYear(new Date()) * 100 + getISOWeek(new Date())
    const index = seed % readingList.length
    return readingList[index]
  }, [readingList])

  const thesisCurrentStreak = useMemo(() => {
    const days = new Set(thesisLogs.map((log) => log.date))
    let streak = 0

    for (let offset = 0; offset < 365; offset += 1) {
      const day = format(subDays(new Date(), offset), 'yyyy-MM-dd')
      if (days.has(day)) {
        streak += 1
      } else {
        break
      }
    }

    return streak
  }, [thesisLogs])

  const tasksDoneThisWeek = useMemo(
    () =>
      doneTasks.filter((task) => {
        if (!task.completed_at) {
          return false
        }
        const day = format(parseISO(task.completed_at), 'yyyy-MM-dd')
        return day >= thisWeekStart && day <= thisWeekEnd
      }).length,
    [doneTasks, thisWeekEnd, thisWeekStart],
  )

  const xpPoints = useMemo(() => {
    const taskScore = tasksDoneThisWeek * 18
    const gymScore = gymThisWeek.length * 90
    const thesisScore = Math.floor(thesisWordsThisWeek / 20)
    const streakBonus = (thesisCurrentStreak + gymCurrentStreak) * 6
    return taskScore + gymScore + thesisScore + streakBonus
  }, [gymCurrentStreak, gymThisWeek.length, tasksDoneThisWeek, thesisCurrentStreak, thesisWordsThisWeek])

  const level = Math.floor(xpPoints / 280) + 1
  const xpIntoLevel = xpPoints % 280
  const xpForNextLevel = 280
  const levelProgress = clampPercentage((xpIntoLevel / xpForNextLevel) * 100)

  const badges = useMemo(() => {
    const list: string[] = []

    if (tasksDoneThisWeek >= 5) {
      list.push('Sprint productif')
    }
    if (thesisCurrentStreak >= 3) {
      list.push('Plume en feu')
    }
    if (gymThisWeek.length >= 2) {
      list.push('Régularité salle')
    }
    if (thesisWordsThisWeek >= 1200) {
      list.push('Cap 1200 mots')
    }

    if (list.length === 0) {
      list.push('Nouveau cycle')
    }

    return list
  }, [gymThisWeek.length, tasksDoneThisWeek, thesisCurrentStreak, thesisWordsThisWeek])

  const dailyQuests = useMemo(
    () => [
      {
        label: 'Valider 1 tâche prioritaire',
        done: doneTasks.some(
          (task) => task.priority === 'high' && task.completed_at && format(parseISO(task.completed_at), 'yyyy-MM-dd') === today,
        ),
      },
      {
        label: 'Écrire une note de thèse aujourd’hui',
        done: thesisToday.length > 0,
      },
      {
        label: 'Planifier ou faire une séance salle',
        done: gymThisWeek.length > 0 || activeGymDraft !== null,
      },
    ],
    [activeGymDraft, doneTasks, gymThisWeek.length, thesisToday.length, today],
  )

  const updateTask = async (taskId: string, patch: Partial<TaskRecord>) => {
    const source = tasks.find((task) => task.id === taskId)
    if (!source) {
      return
    }

    const next: TaskRecord = {
      ...source,
      ...patch,
      updated_at: nowIso(),
    }

    if (patch.status === 'done') {
      next.completed_at = source.completed_at || nowIso()
    }

    if (patch.status === 'todo') {
      next.completed_at = null
    }

    await putTaskLocal(next, true)
    if (sessionUserId) {
      void fireSync(sessionUserId)
    }
  }

  const handleCreateTask = async (event: React.FormEvent) => {
    event.preventDefault()

    if (!sessionUserId || !taskForm.title.trim()) {
      return
    }

    let scheduledDate: string | null = today
    if (taskForm.plan === 'week') {
      scheduledDate = taskForm.weekDate || defaultWeekDate
    }
    if (taskForm.plan === 'custom') {
      scheduledDate = taskForm.customDate || null
    }

    const stamp = nowIso()

    const task: TaskRecord = {
      id: crypto.randomUUID(),
      user_id: sessionUserId,
      title: taskForm.title.trim(),
      status: 'todo',
      priority: taskForm.priority,
      tags: [],
      scheduled_date: scheduledDate,
      due_time: null,
      estimate_minutes: null,
      energy: null,
      created_at: stamp,
      updated_at: stamp,
      completed_at: null,
      original_scheduled_date: null,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
      top3_slot: null,
      last_notified_at: null,
    }

    await putTaskLocal(task, true)
    setTaskForm(defaultTaskForm(today, defaultWeekDate))
    void fireSync(sessionUserId)
  }

  const handleDeleteTask = async (taskId: string) => {
    if (!sessionUserId) {
      return
    }

    await deleteTaskLocal(sessionUserId, taskId, true)
    void fireSync(sessionUserId)
  }

  const handleMoveToToday = async (task: TaskRecord) => {
    const patch: Partial<TaskRecord> = {
      scheduled_date: today,
    }

    if (!task.original_scheduled_date && task.scheduled_date) {
      patch.original_scheduled_date = task.scheduled_date
    }

    await updateTask(task.id, patch)
  }

  const handleMagicLink = async (event: React.FormEvent) => {
    event.preventDefault()

    if (!hasSupabaseClientConfig) {
      setAuthMessage('Variables Supabase manquantes dans .env')
      return
    }

    const email = emailInput.trim()
    if (!email) {
      return
    }

    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: authRedirectTo(),
      },
    })

    if (error) {
      const errorWithStatus = error as { status?: number; message: string }
      const status = errorWithStatus.status ?? 'unknown'
      setAuthMessage(`Erreur login (${status}): ${error.message}`)
      return
    }

    setAuthMessage('Lien magique envoyé. Ouvre ton email sur PC ou iPhone.')
    setEmailInput('')
  }

  const handleLogout = async () => {
    await supabase.auth.signOut()
    setAuthMessage('Session fermée.')
  }

  const handleInstall = async () => {
    if (!installPrompt) {
      setInstallMessage('Sur iPhone: Safari > Partager > Ajouter à l’écran d’accueil.')
      return
    }

    await installPrompt.prompt()
    const result = await installPrompt.userChoice

    if (result.outcome === 'accepted') {
      setInstallMessage('Installation lancée.')
      setInstallPrompt(null)
    } else {
      setInstallMessage('Installation annulée.')
    }
  }

  const handleEnablePush = async () => {
    if (!sessionUserId) {
      setPushMessage('Connecte-toi d’abord pour lier la subscription à ton compte.')
      return
    }

    if (!canUsePush()) {
      setPushMessage('Push non supporté ici. Sur iPhone: Safari + PWA installée + HTTPS.')
      return
    }

    try {
      await requestAndSubscribePush(sessionUserId)
      setPushEnabled(true)
      setPushMessage('Notifications activées pour ce device.')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Impossible d’activer les notifications.'
      setPushMessage(message)
    }
  }

  const handleDisablePush = async () => {
    if (!sessionUserId) {
      return
    }

    await unsubscribePush(sessionUserId)
    setPushEnabled(false)
    setPushMessage('Notifications désactivées pour ce device.')
  }

  const handleExport = async () => {
    if (!sessionUserId) {
      return
    }

    const backup = await serializeBackup(sessionUserId)
    downloadJson(`focus-grid-backup-${today}.json`, backup)
  }

  const handleImportClick = () => {
    fileInputRef.current?.click()
  }

  const handleImportFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!sessionUserId) {
      return
    }

    const file = event.target.files?.[0]
    if (!file) {
      return
    }

    const text = await file.text()

    try {
      const parsed = JSON.parse(text)
      const summary = await importBackupPayload(sessionUserId, parsed)
      setSyncMessage(`Import terminé (${summary.importedTasks} tâches).`)
      void fireSync(sessionUserId)
    } catch {
      setSyncMessage('Fichier invalide, import annulé.')
    }
  }

  const startGymSession = () => {
    if (!gymStartForm.sessionName.trim()) {
      setSyncMessage('Donne un nom à ta séance.')
      return
    }

    setActiveGymDraft({
      date: gymStartForm.date,
      sessionName: gymStartForm.sessionName.trim(),
      durationMinutes: '',
      effort: '3',
      notes: '',
      exercises: [],
    })
    setGymExerciseForm(defaultGymExerciseForm())
    setGymStartForm(defaultGymStartForm(today))
  }

  const addExerciseToActiveSession = () => {
    if (!activeGymDraft || !gymExerciseForm.name.trim()) {
      return
    }

    const exercise: GymExerciseRecord = {
      id: crypto.randomUUID(),
      name: gymExerciseForm.name.trim(),
      sets: gymExerciseForm.sets ? Number(gymExerciseForm.sets) : null,
      reps: gymExerciseForm.reps ? Number(gymExerciseForm.reps) : null,
      weight_kg: gymExerciseForm.weight ? Number(gymExerciseForm.weight) : null,
    }

    setActiveGymDraft((prev) => {
      if (!prev) {
        return null
      }
      return {
        ...prev,
        exercises: [...prev.exercises, exercise],
      }
    })

    setGymExerciseForm(defaultGymExerciseForm())
  }

  const removeExerciseFromActiveSession = (exerciseId: string) => {
    setActiveGymDraft((prev) => {
      if (!prev) {
        return null
      }
      return {
        ...prev,
        exercises: prev.exercises.filter((exercise) => exercise.id !== exerciseId),
      }
    })
  }

  const finishGymSession = async () => {
    if (!sessionUserId || !activeGymDraft) {
      return
    }

    const stamp = nowIso()

    const session: GymSessionRecord = {
      id: crypto.randomUUID(),
      user_id: sessionUserId,
      date: activeGymDraft.date,
      session_name: activeGymDraft.sessionName,
      duration_minutes: activeGymDraft.durationMinutes ? Number(activeGymDraft.durationMinutes) : null,
      effort_1_to_5: activeGymDraft.effort ? Number(activeGymDraft.effort) : null,
      notes: activeGymDraft.notes.trim(),
      exercises: activeGymDraft.exercises,
      created_at: stamp,
      updated_at: stamp,
    }

    await db.gymSessions.put(session)
    setActiveGymDraft(null)
    setGymExerciseForm(defaultGymExerciseForm())
  }

  const cancelGymSession = () => {
    setActiveGymDraft(null)
    setGymExerciseForm(defaultGymExerciseForm())
  }

  const deleteGymSession = async (sessionId: string) => {
    await db.gymSessions.delete(sessionId)
  }

  const saveThesisLog = async (event: React.FormEvent) => {
    event.preventDefault()

    if (!sessionUserId) {
      return
    }

    const stamp = nowIso()
    const entry: ThesisLogRecord = {
      id: crypto.randomUUID(),
      user_id: sessionUserId,
      date: thesisForm.date,
      focus_minutes: 0,
      words_written: thesisForm.wordsWritten ? Number(thesisForm.wordsWritten) : 0,
      note: thesisForm.note.trim(),
      created_at: stamp,
      updated_at: stamp,
    }

    await db.thesisLogs.put(entry)
    setThesisForm(defaultThesisForm(today))
  }

  const addReadingArticle = (event: React.FormEvent) => {
    event.preventDefault()

    const title = readingDraftTitle.trim()
    const rawUrl = readingDraftUrl.trim()

    if (!title || !rawUrl) {
      return
    }

    const url = /^https?:\/\//i.test(rawUrl) ? rawUrl : `https://${rawUrl}`

    setReadingList((prev) => [
      { id: crypto.randomUUID(), title, url },
      ...prev,
    ])
    setReadingDraftTitle('')
    setReadingDraftUrl('')
  }

  const removeReadingArticle = (articleId: string) => {
    setReadingList((prev) => prev.filter((article) => article.id !== articleId))
  }

  const addWeeklyReadingTask = async () => {
    if (!sessionUserId || !weeklyReadingArticle) {
      return
    }

    const title = `Lire: ${weeklyReadingArticle.title}`
    const alreadyExists = openTasks.some((task) => task.title === title)
    if (alreadyExists) {
      setSyncMessage('La tâche de lecture de la semaine existe déjà.')
      return
    }

    const stamp = nowIso()
    const task: TaskRecord = {
      id: crypto.randomUUID(),
      user_id: sessionUserId,
      title,
      status: 'todo',
      priority: 'medium',
      tags: [],
      scheduled_date: today,
      due_time: null,
      estimate_minutes: null,
      energy: null,
      created_at: stamp,
      updated_at: stamp,
      completed_at: null,
      original_scheduled_date: null,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
      top3_slot: null,
      last_notified_at: null,
    }

    await putTaskLocal(task, true)
    void fireSync(sessionUserId)
    setSyncMessage('Tâche lecture ajoutée dans Aujourd’hui.')
  }

  const deleteThesisLog = async (entryId: string) => {
    await db.thesisLogs.delete(entryId)
  }

  const renderTaskCard = (task: TaskRecord) => {
    const overdue = Boolean(task.scheduled_date && task.scheduled_date < today)
    const isDone = task.status === 'done'

    return (
      <div
        key={task.id}
        className={`rounded-xl border p-3 ${
          isDone
            ? 'border-emerald-200 bg-emerald-50/70'
            : overdue
              ? 'border-rose-200 bg-rose-50/70'
              : 'border-slate-200 bg-white'
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${priorityStyle[task.priority]}`}>
                {task.priority === 'high' ? 'Priorité haute' : task.priority === 'medium' ? 'Priorité moyenne' : 'Priorité normale'}
              </span>
              {task.priority === 'high' && <Flame className="h-4 w-4 text-rose-500" />}
              {task.priority === 'medium' && <Star className="h-4 w-4 text-amber-500" />}
            </div>
            <p className={`text-sm ${isDone ? 'line-through text-slate-500' : 'text-slate-800'}`}>{task.title}</p>
            <p className="text-xs text-slate-500">
              {toPrettyDate(task.scheduled_date)}
              {overdue && !isDone ? ' • En retard' : ''}
            </p>
          </div>

          <div className="flex flex-col items-end gap-2">
            <button
              type="button"
              onClick={() => void updateTask(task.id, { status: isDone ? 'todo' : 'done' })}
              className={`rounded-md border px-2 py-1 text-xs ${
                isDone ? 'border-emerald-300 bg-emerald-100 text-emerald-700' : 'border-slate-300 text-slate-600'
              }`}
            >
              {isDone ? 'Reouvrir' : 'Done'}
            </button>

            {overdue && !isDone && (
              <button
                type="button"
                onClick={() => void handleMoveToToday(task)}
                className="rounded-md border border-rose-300 bg-rose-100 px-2 py-1 text-xs text-rose-700"
              >
                Mettre à aujourd’hui
              </button>
            )}

            <button
              type="button"
              onClick={() => void handleDeleteTask(task.id)}
              className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-400 hover:text-rose-600"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!hasSupabaseClientConfig) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-3xl items-center justify-center px-4 py-10">
        <section className="card-panel w-full max-w-2xl space-y-4">
          <h1 className="font-display text-2xl">Configuration requise</h1>
          <p className="text-sm text-slate-700">
            L’app ne peut pas démarrer sans variables Supabase. Crée le fichier
            <code className="mx-1 rounded bg-slate-100 px-1 py-0.5">.env</code>
            dans
            <code className="mx-1 rounded bg-slate-100 px-1 py-0.5">/Users/aurelieneberhardt/Desktop/Codex/dashboard-pwa</code>
            avec:
          </p>
          <pre className="overflow-x-auto rounded-xl bg-slate-900 p-4 text-xs text-slate-100">
{`VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
VITE_VAPID_PUBLIC_KEY=YOUR_VAPID_PUBLIC_KEY`}
          </pre>
          <p className="text-xs text-slate-600">Variables manquantes: {missingClientEnv.join(', ') || 'aucune'}</p>
          <p className="text-xs text-slate-600">
            Ensuite relance <code className="rounded bg-slate-100 px-1 py-0.5">npm run dev</code>.
          </p>
        </section>
      </div>
    )
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 pb-28 pt-4 font-body text-ink sm:px-6">
      <header className="card-panel sticky top-3 z-20 mb-4 flex flex-wrap items-center justify-between gap-3 bg-white/95 backdrop-blur">
        <div>
          <p className="font-display text-xl font-bold">Tableau Perso</p>
          <p className="text-xs text-slate-500">{sessionEmail ?? 'Session non connectée'}</p>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className={`rounded-full px-2 py-1 font-medium ${isOnline ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
            {isOnline ? (
              <span className="inline-flex items-center gap-1">
                <Cloud className="h-3.5 w-3.5" /> En ligne
              </span>
            ) : (
              <span className="inline-flex items-center gap-1">
                <CloudOff className="h-3.5 w-3.5" /> Hors ligne
              </span>
            )}
          </span>

          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-slate-600"
            onClick={() => sessionUserId && void fireSync(sessionUserId)}
            disabled={!sessionUserId || syncInProgress}
          >
            {syncInProgress ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Sync
          </button>

          <span className="text-slate-400">Queue: {queueCount}</span>
        </div>
      </header>

      {!sessionUserId ? (
        <section className="card-panel mx-auto w-full max-w-xl space-y-4">
          <h1 className="font-display text-2xl">Connexion Magic Link</h1>
          <p className="text-sm text-slate-600">Connecte-toi avec le même email sur PC et iPhone pour retrouver exactement les mêmes tâches.</p>
          <form className="space-y-3" onSubmit={handleMagicLink}>
            <input
              type="email"
              placeholder="ton@email.com"
              value={emailInput}
              onChange={(event) => setEmailInput(event.target.value)}
              required
              className="w-full"
            />
            <button
              type="submit"
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent/90"
            >
              <Send className="h-4 w-4" /> Envoyer le lien
            </button>
          </form>
          {authMessage && <p className="text-sm text-slate-600">{authMessage}</p>}
        </section>
      ) : (
        <>
          {activeTab === 'tasks' && (
            <section className="mb-4 rounded-3xl border border-teal-200 bg-gradient-to-r from-teal-600 via-cyan-600 to-emerald-600 p-5 text-white shadow-card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wide text-white/80">Mode progression</p>
                <h2 className="font-display text-2xl">Niveau {level}</h2>
                <p className="text-sm text-white/85">{xpPoints} XP total • Objectif: thèse + régularité salle</p>
              </div>
              <div className="rounded-xl bg-white/15 px-3 py-2 text-sm">
                <p className="inline-flex items-center gap-1 font-semibold">
                  <Trophy className="h-4 w-4" /> {badges[0]}
                </p>
              </div>
            </div>

            <div className="mt-3 h-2 rounded-full bg-white/20">
              <div className="h-2 rounded-full bg-white" style={{ width: `${levelProgress}%` }} />
            </div>
            <p className="mt-1 text-xs text-white/80">
              {xpForNextLevel - xpIntoLevel} XP avant niveau {level + 1}
            </p>

            <div className="mt-3 flex flex-wrap gap-2">
              {badges.map((badge) => (
                <span key={badge} className="rounded-full border border-white/40 bg-white/15 px-3 py-1 text-xs">
                  {badge}
                </span>
              ))}
            </div>

            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              {dailyQuests.map((quest) => (
                <div
                  key={quest.label}
                  className={`rounded-xl border px-3 py-2 text-sm ${
                    quest.done ? 'border-emerald-300 bg-emerald-100/20 text-emerald-50' : 'border-white/30 bg-white/10 text-white'
                  }`}
                >
                  <p className="inline-flex items-center gap-1">
                    <Sparkles className="h-3.5 w-3.5" /> {quest.label}
                  </p>
                </div>
              ))}
            </div>
            </section>
          )}

          <main className="grid flex-1 gap-4">
            {activeTab === 'tasks' && (
              <section className="space-y-4">
                <div className="card-panel space-y-3">
                  <h2 className="font-display text-lg">Ajouter une tâche</h2>
                  <form className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" onSubmit={handleCreateTask}>
                    <input
                      type="text"
                      className="sm:col-span-2"
                      placeholder="Ex: Lire 3 pages / envoyer un mail"
                      value={taskForm.title}
                      onChange={(event) => setTaskForm((prev) => ({ ...prev, title: event.target.value }))}
                      required
                    />

                    <select
                      value={taskForm.plan}
                      onChange={(event) => setTaskForm((prev) => ({ ...prev, plan: event.target.value as TaskPlan }))}
                    >
                      <option value="today">À faire aujourd’hui</option>
                      <option value="week">À faire cette semaine</option>
                      <option value="custom">Date personnalisée</option>
                    </select>

                    {taskForm.plan === 'week' ? (
                      <select
                        value={taskForm.weekDate}
                        onChange={(event) => setTaskForm((prev) => ({ ...prev, weekDate: event.target.value }))}
                      >
                        {weekDays.map((day) => (
                          <option key={day.date} value={day.date}>
                            {day.label}
                          </option>
                        ))}
                      </select>
                    ) : taskForm.plan === 'custom' ? (
                      <input
                        type="date"
                        value={taskForm.customDate}
                        onChange={(event) => setTaskForm((prev) => ({ ...prev, customDate: event.target.value }))}
                      />
                    ) : (
                      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500">Aujourd’hui</div>
                    )}

                    <select
                      value={taskForm.priority}
                      onChange={(event) => setTaskForm((prev) => ({ ...prev, priority: event.target.value as TaskPriority }))}
                    >
                      <option value="high">Priorité haute</option>
                      <option value="medium">Priorité moyenne</option>
                      <option value="normal">Priorité normale</option>
                    </select>

                    <button
                      type="submit"
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                    >
                      <Plus className="h-4 w-4" /> Ajouter
                    </button>
                  </form>
                </div>

                {visibleTaskSections.length > 0 ? (
                  <div className="grid gap-3 lg:grid-cols-2">
                    {visibleTaskSections.map((section) => (
                      <div key={section.key} className="card-panel space-y-2">
                        <h3 className="font-display text-base">
                          {section.title} ({section.items.length})
                        </h3>
                        {section.items.map((task) => renderTaskCard(task))}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="card-panel">
                    <p className="text-sm text-slate-500">Aucune tâche active pour le moment. Ajoute ta prochaine action.</p>
                  </div>
                )}

                {doneTasks.length > 0 && (
                  <div className="card-panel space-y-2">
                    <h3 className="font-display text-base">Terminé récemment ({doneTasks.length})</h3>
                    {doneTasks.slice(0, 8).map((task) => renderTaskCard(task))}
                  </div>
                )}
              </section>
            )}

            {activeTab === 'calendar' && (
              <section className="space-y-4">
                <div className="card-panel space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => setMonthCursor((prev) => addMonths(prev, -1))}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700"
                    >
                      Mois précédent
                    </button>
                    <h2 className="font-display text-lg capitalize">{format(monthCursor, 'MMMM yyyy')}</h2>
                    <button
                      type="button"
                      onClick={() => setMonthCursor((prev) => addMonths(prev, 1))}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700"
                    >
                      Mois suivant
                    </button>
                  </div>

                  <div className="grid grid-cols-7 gap-1">
                    {calendarGrid.map((day) => {
                      const doneCount = completedCountByDate.get(day.date) ?? 0
                      const hasPlanned = tasks.some((task) => task.scheduled_date === day.date)
                      const isSelected = selectedCalendarDay === day.date
                      const intensityClass =
                        doneCount >= 4
                          ? 'bg-emerald-500 text-white'
                          : doneCount >= 2
                            ? 'bg-emerald-300 text-slate-900'
                            : doneCount >= 1
                              ? 'bg-emerald-100 text-slate-800'
                              : hasPlanned
                                ? 'bg-amber-100 text-amber-900'
                                : 'bg-slate-100 text-slate-500'

                      return (
                        <button
                          key={day.date}
                          type="button"
                          onClick={() => setSelectedCalendarDay(day.date)}
                          className={`rounded-lg border px-1 py-2 text-center text-xs transition ${
                            day.inMonth ? '' : 'opacity-45'
                          } ${isSelected ? 'border-accent ring-2 ring-accent/20' : 'border-transparent'} ${intensityClass}`}
                        >
                          <div>{day.dayNumber}</div>
                          <div className="text-[10px]">{doneCount}</div>
                        </button>
                      )
                    })}
                  </div>
                </div>

                <div className="grid gap-3 lg:grid-cols-3">
                  <div className="card-panel space-y-2">
                    <h3 className="font-display text-base">Faites ({calendarDoneTasks.length})</h3>
                    {calendarDoneTasks.length === 0 ? (
                      <p className="text-sm text-slate-500">Aucune tâche faite ce jour.</p>
                    ) : (
                      calendarDoneTasks.map((task) => renderTaskCard(task))
                    )}
                  </div>

                  <div className="card-panel space-y-2">
                    <h3 className="font-display text-base">Planifiées ({calendarPlannedTasks.length})</h3>
                    {calendarPlannedTasks.length === 0 ? (
                      <p className="text-sm text-slate-500">Aucune tâche planifiée ce jour.</p>
                    ) : (
                      calendarPlannedTasks.map((task) => renderTaskCard(task))
                    )}
                  </div>

                  <div className="card-panel space-y-2">
                    <h3 className="font-display text-base">En retard ({calendarOverdueTasks.length})</h3>
                    {calendarOverdueTasks.length === 0 ? (
                      <p className="text-sm text-slate-500">Aucun retard avant ce jour.</p>
                    ) : (
                      calendarOverdueTasks.map((task) => renderTaskCard(task))
                    )}
                  </div>
                </div>
              </section>
            )}

            {activeTab === 'gym' && (
              <section className="space-y-4">
                {!activeGymDraft ? (
                  <div className="card-panel space-y-3">
                    <h2 className="font-display text-lg">Nouvelle séance</h2>
                    <p className="text-sm text-slate-600">1) Donne un nom à la séance. 2) Clique "Démarrer". 3) Ajoute tes exercices.</p>
                    <div className="grid gap-2 sm:grid-cols-3">
                      <input
                        type="date"
                        value={gymStartForm.date}
                        onChange={(event) => setGymStartForm((prev) => ({ ...prev, date: event.target.value }))}
                      />
                      <input
                        type="text"
                        placeholder="Ex: Upper A, Jambes"
                        value={gymStartForm.sessionName}
                        onChange={(event) => setGymStartForm((prev) => ({ ...prev, sessionName: event.target.value }))}
                      />
                      <button
                        type="button"
                        onClick={startGymSession}
                        className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                      >
                        <Plus className="h-4 w-4" /> Démarrer
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="card-panel space-y-3 border-teal-200 bg-teal-50/40">
                    <h2 className="font-display text-lg">Séance en cours: {activeGymDraft.sessionName}</h2>
                    <div className="grid gap-2 sm:grid-cols-4">
                      <input type="date" value={activeGymDraft.date} onChange={(event) => setActiveGymDraft((prev) => (prev ? { ...prev, date: event.target.value } : prev))} />
                      <input
                        type="number"
                        min={0}
                        placeholder="Durée (min)"
                        value={activeGymDraft.durationMinutes}
                        onChange={(event) => setActiveGymDraft((prev) => (prev ? { ...prev, durationMinutes: event.target.value } : prev))}
                      />
                      <select value={activeGymDraft.effort} onChange={(event) => setActiveGymDraft((prev) => (prev ? { ...prev, effort: event.target.value } : prev))}>
                        <option value="1">Effort 1/5</option>
                        <option value="2">Effort 2/5</option>
                        <option value="3">Effort 3/5</option>
                        <option value="4">Effort 4/5</option>
                        <option value="5">Effort 5/5</option>
                      </select>
                      <div className="rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm text-teal-700">
                        {activeGymDraft.exercises.length} exo(s)
                      </div>
                    </div>

                    <div className="grid gap-2 sm:grid-cols-5">
                      <input
                        type="text"
                        placeholder="Exercice"
                        value={gymExerciseForm.name}
                        onChange={(event) => setGymExerciseForm((prev) => ({ ...prev, name: event.target.value }))}
                      />
                      <input
                        type="number"
                        min={0}
                        placeholder="Séries"
                        value={gymExerciseForm.sets}
                        onChange={(event) => setGymExerciseForm((prev) => ({ ...prev, sets: event.target.value }))}
                      />
                      <input
                        type="number"
                        min={0}
                        placeholder="Reps"
                        value={gymExerciseForm.reps}
                        onChange={(event) => setGymExerciseForm((prev) => ({ ...prev, reps: event.target.value }))}
                      />
                      <input
                        type="number"
                        min={0}
                        step="0.5"
                        placeholder="Poids (kg)"
                        value={gymExerciseForm.weight}
                        onChange={(event) => setGymExerciseForm((prev) => ({ ...prev, weight: event.target.value }))}
                      />
                      <button
                        type="button"
                        onClick={addExerciseToActiveSession}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-teal-300 bg-white px-3 py-2 text-sm font-semibold text-teal-700"
                      >
                        + Ajouter exo
                      </button>
                    </div>

                    <textarea
                      rows={3}
                      placeholder="Notes séance"
                      value={activeGymDraft.notes}
                      onChange={(event) => setActiveGymDraft((prev) => (prev ? { ...prev, notes: event.target.value } : prev))}
                    />

                    <div className="space-y-2">
                      {activeGymDraft.exercises.length === 0 ? (
                        <p className="text-sm text-slate-500">Ajoute au moins un exercice pour suivre ta progression.</p>
                      ) : (
                        activeGymDraft.exercises.map((exercise) => (
                          <div key={exercise.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                            <span>
                              {exercise.name} • {exercise.sets ?? '-'}x{exercise.reps ?? '-'} • {exercise.weight_kg ?? '-'} kg
                            </span>
                            <button type="button" onClick={() => removeExerciseFromActiveSession(exercise.id)} className="text-xs text-rose-600">
                              retirer
                            </button>
                          </div>
                        ))
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void finishGymSession()}
                        className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                      >
                        Sauvegarder la séance
                      </button>
                      <button type="button" onClick={cancelGymSession} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600">
                        Annuler
                      </button>
                    </div>
                  </div>
                )}

                <div className="grid gap-3 lg:grid-cols-3">
                  <div className="card-panel">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Semaine</p>
                    <p className="mt-1 text-lg font-semibold">{gymThisWeek.length} séance(s)</p>
                    <div className="mt-2 h-2 rounded-full bg-slate-100">
                      <div
                        className="h-2 rounded-full bg-accent"
                        style={{ width: `${clampPercentage((gymThisWeek.length / 3) * 100)}%` }}
                      />
                    </div>
                    <p className="mt-2 text-xs text-slate-500">Objectif fun: 3 séances = jauge pleine.</p>
                  </div>

                  <div className="card-panel">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Série actuelle</p>
                    <p className="mt-1 text-lg font-semibold">{gymCurrentStreak} jour(s) d’affilée</p>
                    <p className="text-xs text-slate-500">Chaque jour avec au moins une séance compte.</p>
                  </div>

                  <div className="card-panel">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Volume 30 jours</p>
                    <p className="mt-1 text-lg font-semibold">{Math.round(gymVolumeLast30)} kg</p>
                    <p className="text-xs text-slate-500">Basé sur séries x reps x poids.</p>
                  </div>
                </div>

                <div className="card-panel space-y-2">
                  <h3 className="font-display text-base">Historique récent</h3>
                  {gymSessions.length === 0 ? (
                    <p className="text-sm text-slate-500">Aucune séance pour le moment.</p>
                  ) : (
                    gymSessions.slice(0, 12).map((session) => (
                      <div key={session.id} className="rounded-xl border border-slate-200 bg-white p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-slate-800">{session.session_name}</p>
                            <p className="text-xs text-slate-500">
                              {toPrettyDate(session.date)}
                              {session.duration_minutes ? ` • ${session.duration_minutes} min` : ''}
                              {session.effort_1_to_5 ? ` • effort ${session.effort_1_to_5}/5` : ''}
                            </p>
                            {session.notes && <p className="mt-1 text-sm text-slate-600 whitespace-pre-wrap">{session.notes}</p>}
                            {session.exercises.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {session.exercises.map((exercise) => (
                                  <span key={exercise.id} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                                    {exercise.name} {exercise.weight_kg ?? '-'}kg
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                          <button
                            type="button"
                            onClick={() => void deleteGymSession(session.id)}
                            className="rounded-md border border-slate-200 p-1 text-slate-400 hover:text-rose-600"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </section>
            )}

            {activeTab === 'thesis' && (
              <section className="space-y-4">
                <div className="card-panel space-y-3">
                  <h2 className="font-display text-lg">Journal de thèse</h2>
                  <p className="text-sm text-slate-600">Simple: date, nombre de mots, note. Pas de minutes à saisir.</p>
                  <form className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" onSubmit={saveThesisLog}>
                    <input
                      type="date"
                      value={thesisForm.date}
                      onChange={(event) => setThesisForm((prev) => ({ ...prev, date: event.target.value }))}
                    />
                    <input
                      type="number"
                      min={0}
                      placeholder="Mots écrits"
                      value={thesisForm.wordsWritten}
                      onChange={(event) => setThesisForm((prev) => ({ ...prev, wordsWritten: event.target.value }))}
                    />
                    <button
                      type="submit"
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                    >
                      <Plus className="h-4 w-4" /> Ajouter entrée
                    </button>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                      Entrées cette semaine: {thesisThisWeek.length}
                    </div>

                    <textarea
                      className="sm:col-span-2 lg:col-span-4"
                      rows={4}
                      placeholder="Ce qui a avancé aujourd’hui, blocage, prochaine action."
                      value={thesisForm.note}
                      onChange={(event) => setThesisForm((prev) => ({ ...prev, note: event.target.value }))}
                    />
                  </form>
                </div>

                <div className="grid gap-3 lg:grid-cols-3">
                  <div className="card-panel">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Mots semaine</p>
                    <p className="mt-1 text-lg font-semibold">{thesisWordsThisWeek}</p>
                  </div>
                  <div className="card-panel">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Régularité</p>
                    <p className="mt-1 text-lg font-semibold">{thesisCurrentStreak} jour(s) d’affilée</p>
                  </div>
                  <div className="card-panel">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Entrée du jour</p>
                    <p className="mt-1 text-lg font-semibold">{thesisToday.length > 0 ? 'Oui' : 'Pas encore'}</p>
                  </div>
                </div>

                <div className="card-panel space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="font-display text-base">Article de la semaine</h3>
                      <p className="text-xs text-slate-500">Sélection automatique depuis ta liste de lecture.</p>
                    </div>
                    {weeklyReadingArticle && (
                      <button
                        type="button"
                        onClick={() => void addWeeklyReadingTask()}
                        className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700"
                      >
                        Ajouter en tâche
                      </button>
                    )}
                  </div>

                  {weeklyReadingArticle ? (
                    <div className="rounded-xl border border-teal-200 bg-teal-50 p-3">
                      <p className="font-semibold text-slate-800">{weeklyReadingArticle.title}</p>
                      <a
                        href={weeklyReadingArticle.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1 inline-block text-sm text-teal-700 underline"
                      >
                        Ouvrir l’article
                      </a>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500">Ajoute des articles ci-dessous pour générer une recommandation hebdo.</p>
                  )}

                  <form className="grid gap-2 sm:grid-cols-3" onSubmit={addReadingArticle}>
                    <input
                      type="text"
                      placeholder="Titre de l’article"
                      value={readingDraftTitle}
                      onChange={(event) => setReadingDraftTitle(event.target.value)}
                      required
                    />
                    <input
                      type="text"
                      placeholder="URL"
                      value={readingDraftUrl}
                      onChange={(event) => setReadingDraftUrl(event.target.value)}
                      required
                    />
                    <button
                      type="submit"
                      className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700"
                    >
                      <Plus className="h-4 w-4" /> Ajouter à la liste
                    </button>
                  </form>

                  {readingList.length > 0 && (
                    <div className="space-y-2">
                      {readingList.slice(0, 10).map((article) => (
                        <div key={article.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                          <a href={article.url} target="_blank" rel="noreferrer" className="line-clamp-1 text-slate-700 hover:underline">
                            {article.title}
                          </a>
                          <button
                            type="button"
                            onClick={() => removeReadingArticle(article.id)}
                            className="text-xs text-rose-600"
                          >
                            retirer
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="card-panel space-y-2">
                  <h3 className="font-display text-base">Entrées récentes</h3>
                  {thesisLogs.length === 0 ? (
                    <p className="text-sm text-slate-500">Aucune entrée pour l’instant.</p>
                  ) : (
                    thesisLogs.slice(0, 14).map((entry) => (
                      <div key={entry.id} className="rounded-xl border border-slate-200 bg-white p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-slate-800">{toPrettyDate(entry.date)}</p>
                            <p className="text-xs text-slate-500">{entry.words_written} mots</p>
                            {entry.note && <p className="mt-1 text-sm text-slate-600 whitespace-pre-wrap">{entry.note}</p>}
                          </div>
                          <button
                            type="button"
                            onClick={() => void deleteThesisLog(entry.id)}
                            className="rounded-md border border-slate-200 p-1 text-slate-400 hover:text-rose-600"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </section>
            )}

            {activeTab === 'settings' && (
              <section className="space-y-4">
                <div className="card-panel space-y-3">
                  <h2 className="font-display text-lg">Compte & Sync</h2>
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-600">{sessionEmail}</span>
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-slate-700"
                    >
                      <LogOut className="h-4 w-4" /> Se déconnecter
                    </button>
                  </div>
                  <p className="text-xs text-slate-500">Dernière sync: {lastSyncAt ? formatStatusDate(lastSyncAt) : 'jamais'}</p>
                </div>

                <div className="card-panel space-y-3">
                  <h2 className="font-display text-lg">Installer l’app</h2>
                  <button type="button" onClick={() => void handleInstall()} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white">
                    Installer sur cet appareil
                  </button>
                  <p className="text-xs text-slate-600">iPhone: Safari &gt; Partager &gt; Ajouter à l’écran d’accueil.</p>
                  {installMessage && <p className="text-xs text-slate-600">{installMessage}</p>}
                </div>

                <div className="card-panel space-y-3">
                  <h2 className="font-display text-lg">Notifications push</h2>
                  <p className="text-xs text-slate-600">iOS nécessite HTTPS + app installée en PWA + clic explicite sur le bouton ci-dessous.</p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void handleEnablePush()}
                      className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white"
                    >
                      <Bell className="h-4 w-4" /> Activer les notifications
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDisablePush()}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm"
                    >
                      <BellOff className="h-4 w-4" /> Désactiver
                    </button>
                  </div>
                  <p className="text-xs text-slate-600">Statut local: {pushEnabled ? 'Activé' : 'Inactif'}</p>
                  {pushMessage && <p className="text-xs text-slate-600">{pushMessage}</p>}
                </div>

                <div className="card-panel space-y-3">
                  <h2 className="font-display text-lg">Backup JSON</h2>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => void handleExport()} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm">
                      <Download className="h-4 w-4" /> Exporter
                    </button>
                    <button type="button" onClick={handleImportClick} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm">
                      <Upload className="h-4 w-4" /> Importer
                    </button>
                    <input ref={fileInputRef} type="file" accept="application/json" className="hidden" onChange={handleImportFile} />
                  </div>
                  <p className="text-xs text-slate-600">Inclut tâches, salle, thèse et backup legacy `fg_*`.</p>
                </div>
              </section>
            )}
          </main>

          <nav className="fixed bottom-3 left-1/2 z-30 flex w-[calc(100%-1.5rem)] max-w-3xl -translate-x-1/2 gap-2 rounded-2xl border border-slate-200 bg-white/95 p-2 shadow-card backdrop-blur sm:w-[calc(100%-3rem)]">
            {APP_TABS.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-2 py-2 text-sm transition ${
                    activeTab === tab.key ? 'bg-accent text-white' : 'bg-transparent text-slate-500 hover:bg-slate-100'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{tab.label}</span>
                </button>
              )
            })}
          </nav>
        </>
      )}

      {(syncMessage || authMessage) && (
        <div className="pointer-events-none fixed right-4 top-4 z-40 rounded-lg bg-slate-900 px-3 py-2 text-xs text-white shadow-lg">
          {syncMessage || authMessage}
        </div>
      )}

      {!sessionUserId && (
        <footer className="mx-auto mt-8 text-center text-xs text-slate-500">
          <p className="inline-flex items-center gap-1">
            <LogIn className="h-3.5 w-3.5" /> Connecte-toi pour déclencher migration, sync et notifications.
          </p>
        </footer>
      )}
    </div>
  )
}

export default App
