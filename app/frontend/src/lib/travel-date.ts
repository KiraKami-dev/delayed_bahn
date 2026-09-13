export function germanTime(date: string, hhmm: string): string {
  const target = Date.parse(`${date}T${hhmm}:00Z`)
  let stamp = target
  const formatter = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" })
  for (let i = 0; i < 3; i++) {
    const local = formatter.format(new Date(stamp)).replace(" ", "T")
    const difference = target - Date.parse(`${local}Z`)
    if (difference === 0) return new Date(stamp).toISOString()
    stamp += difference
  }
  throw new Error("That time does not exist in Germany because the clocks change. Please check the timetable.")
}

export function germanyDate(now = new Date()): string {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
}
export function dateDeparture(date: string, now = new Date()): string {
  const today = germanyDate(now)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date < today) throw new Error('Choose today or a future travel date.')
  if (date === today) return now.toISOString()
  const departure = germanTime(date, '08:00')
  if (germanyDate(new Date(departure)) !== date) throw new Error('Choose a valid travel date.')
  return departure
}
