import { Volume2 } from 'lucide-react'
import { useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { api, type Language } from '../api'
import { useToast } from './Toast'

type Variant = 'primary' | 'secondary' | 'ghost'

const variants: Record<Variant, string> = {
  primary:
    'bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white shadow-sm',
  secondary:
    'bg-white text-zinc-800 ring-1 ring-zinc-200 hover:bg-zinc-50 dark:bg-zinc-900 dark:text-zinc-100 dark:ring-zinc-800 dark:hover:bg-zinc-800 shadow-sm',
  ghost: 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100',
}

export function Button({
  variant = 'secondary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-500 disabled:pointer-events-none disabled:opacity-50 ${variants[variant]} ${className}`}
    />
  )
}

export const inputClass =
  'w-full rounded-md bg-white px-2.5 py-1.5 text-sm ring-1 ring-zinc-200 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:bg-zinc-900 dark:ring-zinc-800 dark:placeholder:text-zinc-500 dark:focus:ring-zinc-600'

export function Field({ label, children, className = '' }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block space-y-1 ${className}`}>
      <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{label}</span>
      {children}
    </label>
  )
}

export function Spinner({ className = 'size-4' }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

// Text -> audio URL, so replaying the same text doesn't even hit the server.
const audioUrls = new Map<string, string>()

/** Audio is cached by language and text on both the client and server. */
export function PlayButton({ text, language, disabled }: { text: string; language: Language; disabled?: boolean }) {
  const [busy, setBusy] = useState(false)
  const audio = useRef<HTMLAudioElement | null>(null)
  const toast = useToast()

  async function play() {
    const clean = text.replace(/<[^>]+>/g, '').trim()
    if (!clean) return
    const cacheKey = `${language}:${clean}`
    setBusy(true)
    try {
      let url = audioUrls.get(cacheKey)
      if (!url) {
        url = (await api.speak(clean, language)).url
        audioUrls.set(cacheKey, url)
      }
      audio.current?.pause()
      audio.current = new Audio(url)
      await audio.current.play()
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      onClick={play}
      disabled={disabled || busy || !text.trim()}
      aria-label="Listen"
      title="Listen"
      className="relative inline-flex size-8 shrink-0 items-center justify-center rounded-md text-zinc-500 transition-colors after:absolute after:-inset-1 hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-zinc-500 disabled:opacity-40 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
    >
      {busy ? <Spinner /> : <Volume2 className="size-4" />}
    </button>
  )
}
