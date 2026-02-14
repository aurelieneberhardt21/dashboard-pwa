import {
  addDays,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  startOfMonth,
  startOfWeek,
} from 'date-fns'

export const todayLocalDate = () => format(new Date(), 'yyyy-MM-dd')

export const compareDateStrings = (a: string | null, b: string | null) => {
  if (!a && !b) {
    return 0
  }
  if (!a) {
    return 1
  }
  if (!b) {
    return -1
  }
  return a.localeCompare(b)
}

export const buildMonthGrid = (selectedMonth: Date) => {
  const monthStart = startOfMonth(selectedMonth)
  const monthEnd = endOfMonth(monthStart)
  const gridStart = startOfWeek(monthStart, { weekStartsOn: 1 })
  const gridEnd = endOfWeek(monthEnd, { weekStartsOn: 1 })
  const days: Date[] = []

  let current = gridStart
  while (current <= gridEnd) {
    days.push(current)
    current = addDays(current, 1)
  }

  return days.map((day) => ({
    date: format(day, 'yyyy-MM-dd'),
    dayNumber: format(day, 'd'),
    inMonth: isSameMonth(day, monthStart),
    weekdayShort: format(day, 'EEE'),
  }))
}

export const weekFromToday = () => {
  const start = startOfWeek(new Date(), { weekStartsOn: 1 })
  return Array.from({ length: 7 }, (_, index) => {
    const day = addDays(start, index)
    return {
      date: format(day, 'yyyy-MM-dd'),
      label: format(day, 'EEE d'),
    }
  })
}

export const toTimeInputValue = (value: string | null) => {
  if (!value) {
    return ''
  }
  return value.slice(0, 5)
}

export const priorityRank: Record<string, number> = {
  high: 3,
  medium: 2,
  normal: 1,
}
