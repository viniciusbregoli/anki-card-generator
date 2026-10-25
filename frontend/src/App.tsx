import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type Language, type Status } from './api'
import { BatchItem, type Item } from './components/BatchItem'
import { cardsFor, LANGUAGE_NAMES, PLACEHOLDERS } from './languages'
import { useToast } from './components/Toast'
import { Button, inputClass, Spinner } from './components/ui'

const MAX_LINES = 50
const PARALLEL_DRAFTS = 4

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

export default function App() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [language, setLanguage] = useState<Language>(() => localStorage.getItem('card-language') === 'es' ? 'es' : 'de')
  const status = useQuery({ queryKey: ['status'], queryFn: api.status, refetchInterval: 30_000 })
  const recent = useQuery({ queryKey: ['recent', language], queryFn: () => api.recent(language) })

  const [text, setText] = useState('')
  const [items, setItems] = useState<Item[]>([])
  const [saving, setSaving] = useState(false)
  const [menu, setMenu] = useState<'commands' | 'help' | null>(null)
  const itemsRef = useRef(items)
  const input = useRef<HTMLTextAreaElement>(null)
  const languageInput = useRef<HTMLSelectElement>(null)
  const commandDialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    itemsRef.current = items
  }, [items])

  const update = (id: string, patch: Partial<Item>) =>
    setItems((list) => list.map((it) => (it.id === id ? { ...it, ...patch } : it)))

  async function draftAll(queue: Item[], expandSingle: boolean) {
    const worker = async () => {
      for (let it = queue.shift(); it; it = queue.shift()) {
        update(it.id, { status: 'drafting', error: undefined })
        try {
          const r = await api.draft({ text: it.input, language: it.language })
          update(it.id, {
            status: 'ready',
            result: r,
            draft: r.draft,
            // Words you already have start unticked; tick them to add anyway.
            selected: r.duplicates.length === 0,
            expanded: expandSingle,
          })
        } catch (e) {
          update(it.id, { status: 'failed', error: message(e), selected: false })
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(PARALLEL_DRAFTS, queue.length) }, worker))
  }

  function generate() {
    const seen = new Set<string>()
    const lines = text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l && !seen.has(l.toLowerCase()) && seen.add(l.toLowerCase()))
    if (!lines.length) return
    if (lines.length > MAX_LINES) {
      toast(`At most ${MAX_LINES} lines at a time; the first ${MAX_LINES} were taken.`, 'error')
    }
    const fresh: Item[] = lines.slice(0, MAX_LINES).map((line) => ({
      id: crypto.randomUUID(),
      input: line,
      language,
      status: 'queued',
      selected: false,
      expanded: false,
    }))
    setItems((list) => [...fresh, ...list])
    setText('')
    draftAll([...fresh], fresh.length === 1 && itemsRef.current.length === 0)
  }

  async function save(ids: string[], allowDuplicate = false) {
    setSaving(true)
    let notes = 0
    let cards = 0
    const decks = new Set<string>()
    // One at a time: each save makes up to three audio clips, and the first one
    // also creates the note types and the deck.
    for (const id of ids) {
      const it = itemsRef.current.find((x) => x.id === id)
      if (!it?.draft || it.status !== 'ready') continue
      update(id, { status: 'saving', error: undefined })
      try {
        const saved = await api.save(it.draft, allowDuplicate)
        decks.add(saved.deck)
        update(id, { status: 'saved', selected: false, expanded: false, duplicate: false })
        notes += 1
        cards += cardsFor(it.draft.kind, it.draft.language).length
      } catch (e) {
        const duplicate = e instanceof ApiError && e.code === 'duplicate'
        update(id, {
          status: 'ready',
          selected: false,
          duplicate,
          error: duplicate ? `A ${it.draft.kind} card for “${it.draft.lemma}” already exists.` : message(e),
        })
      }
    }
    setSaving(false)
    queryClient.invalidateQueries({ queryKey: ['recent'] })
    if (notes) toast(`Added ${notes} ${notes === 1 ? 'note' : 'notes'} (${cards} cards) to ${[...decks].join(', ')}`)
  }

  const languageStatus = status.data?.languages[language]
  const deck = languageStatus?.deck ?? `${LANGUAGE_NAMES[language]} - Mine`
  const ready = items.filter((i) => i.status === 'ready')
  const selected = ready.filter((i) => i.selected)
  const selectedCards = selected.reduce((n, i) => n + cardsFor(i.draft!.kind, i.draft!.language).length, 0)
  const pending = items.some((i) => i.status === 'queued' || i.status === 'drafting')
  const done = items.filter((i) => i.status === 'saved').length

  const commands = [
    { key: 'i', label: 'Focus word input', run: () => input.current?.focus() },
    { key: 'l', label: 'Choose card language', run: () => languageInput.current?.focus() },
    { key: 'a', label: 'Add selected notes', disabled: !selected.length || saving, run: () => save(selected.map((i) => i.id)) },
  ]

  useEffect(() => {
    if (menu) commandDialog.current?.showModal()
    else commandDialog.current?.close()
  }, [menu])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.isComposing) return
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setMenu((current) => current ? null : 'commands')
        return
      }
      if (!menu && event.key === 'Escape') {
        setItems((list) => list.map((item) => ({ ...item, expanded: false })))
        return
      }
      const target = event.target as HTMLElement
      if (target.closest('input, textarea, select, [contenteditable="true"]') || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === '?') {
        event.preventDefault()
        setMenu('help')
      } else if (!menu) {
        const command = commands.find((command) => command.key === event.key && !command.disabled)
        if (command) {
          event.preventDefault()
          command.run()
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 sm:py-10">
      <header className="mb-6 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Card Generator</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
            <select
              ref={languageInput}
              aria-label="Card language"
              title="Choose card language (L)"
              value={language}
              onChange={(e) => {
                const next = e.target.value as Language
                setLanguage(next)
                localStorage.setItem('card-language', next)
              }}
              className={`${inputClass.replace('w-full ', '')} w-28`}
            >
              {(Object.entries(LANGUAGE_NAMES) as [Language, string][]).map(([code, name]) => (
                <option key={code} value={code}>{name}</option>
              ))}
            </select>
            <span>New cards go to {deck}</span>
          </div>
        </div>
        <StatusLine status={status.data && { ...status.data, ...languageStatus }} />
      </header>

      <div className="mb-3 flex justify-end">
        <Button variant="ghost" onClick={() => setMenu('commands')} title="Commands (Cmd+K)">
          Commands <kbd className="text-xs">⌘K</kbd>
        </Button>
        <Button variant="ghost" onClick={() => setMenu('help')} title="Keyboard shortcuts (?)">?</Button>
      </div>

      <form
        className="mb-6"
        onSubmit={(e) => {
          e.preventDefault()
          generate()
        }}
      >
        <div className="flex items-start gap-2">
          <textarea
            ref={input}
            autoFocus
            rows={Math.min(8, Math.max(1, text.split('\n').length))}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                generate()
              }
            }}
            placeholder={PLACEHOLDERS[language]}
            aria-label="Words or sentences, one per line"
            lang={language}
            autoCapitalize="off"
            spellCheck={false}
            className={`${inputClass} resize-none py-2 text-base`}
          />
          <Button type="submit" variant="primary" className="px-4 py-2" disabled={!text.trim()}>
            <Sparkles className="size-4" />
            Generate
          </Button>
        </div>
        <p className="mt-1.5 text-xs text-zinc-500 dark:text-zinc-400">
          One word or sentence per line. Paste a list to make many cards; Shift+Enter starts a new line.
        </p>
      </form>

      {items.length > 0 && (
        <section aria-label="Drafts" className="mb-10">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-zinc-500 tabular-nums dark:text-zinc-400">
              {ready.length} ready
              {pending && ' · drafting…'}
              {done > 0 && ` · ${done} added`}
            </p>
            <div className="flex items-center gap-1">
              {ready.length > 1 && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    const all = selected.length < ready.length
                    setItems((list) => list.map((i) => (i.status === 'ready' ? { ...i, selected: all } : i)))
                  }}
                >
                  {selected.length < ready.length ? 'Select all' : 'Select none'}
                </Button>
              )}
              {done > 0 && (
                <Button variant="ghost" onClick={() => setItems((list) => list.filter((i) => i.status !== 'saved'))}>
                  Clear added
                </Button>
              )}
              <Button
                variant="primary"
                disabled={!selected.length || saving}
                onClick={() => save(selected.map((i) => i.id))}
              >
                {saving && <Spinner />}
                {selected.length
                  ? `Add ${selected.length} ${selected.length === 1 ? 'note' : 'notes'} · ${selectedCards} cards`
                  : 'Add'}
              </Button>
            </div>
          </div>
          <ul className="divide-y divide-zinc-100 rounded-lg shadow-sm ring-1 ring-zinc-200 dark:divide-zinc-800 dark:ring-zinc-800">
            {items.map((it) => (
              <BatchItem
                key={it.id}
                item={it}
                onChange={(patch) => update(it.id, patch)}
                onRemove={() => setItems((list) => list.filter((x) => x.id !== it.id))}
                onRetry={() => draftAll([it], false)}
                onAddAnyway={() => save([it.id], true)}
              />
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-medium text-zinc-500 dark:text-zinc-400">Recently added</h2>
        {recent.isPending ? (
          <Spinner />
        ) : recent.isError ? (
          <p className="text-sm text-zinc-500">{recent.error.message}</p>
        ) : recent.data.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Nothing yet. Your first card will show up here.</p>
        ) : (
          <ul className="divide-y divide-zinc-100 rounded-lg bg-white ring-1 ring-zinc-200 dark:divide-zinc-800 dark:bg-zinc-900 dark:ring-zinc-800">
            {recent.data.map((n) => (
              <li key={n.id} className="flex items-baseline justify-between gap-3 px-3 py-2 text-sm">
                <span className="truncate">{n.first_field}</span>
                <span className="shrink-0 text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                  {n.notetype.replace(/^(DE|ES) /, '')} · {new Date(n.created * 1000).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <dialog
        ref={commandDialog}
        aria-labelledby="commands-title"
        onCancel={() => setMenu(null)}
        onClose={() => setMenu(null)}
        className="m-auto w-80 max-w-[calc(100%-2rem)] rounded-lg bg-white p-4 text-zinc-900 shadow-xl backdrop:bg-black/40 dark:bg-zinc-900 dark:text-zinc-100"
      >
        <h2 id="commands-title" className="mb-3 font-semibold">{menu === 'help' ? 'Keyboard shortcuts' : 'Commands'}</h2>
        <div className="flex flex-col gap-1">
          {commands.map((command) => (
            <Button key={command.key} variant="ghost" disabled={command.disabled} className="justify-between" onClick={() => {
              commandDialog.current?.close()
              setMenu(null)
              command.run()
            }}>
              {command.label} <kbd>{command.key.toUpperCase()}</kbd>
            </Button>
          ))}
          <p className="my-2 text-xs text-zinc-500 dark:text-zinc-400">Enter generates. Shift+Enter adds a line. Esc closes a dialog or collapses drafts. Cmd+K opens commands. ? shows shortcuts.</p>
          <Button onClick={() => setMenu(null)}>Close <kbd>Esc</kbd></Button>
        </div>
      </dialog>
    </div>
  )
}

function StatusLine({ status }: { status?: Status }) {
  if (!status) return null
  const items: { label: string; ok: boolean; title: string }[] = [
    { label: 'Text', ok: status.text_model.configured, title: status.text_model.model },
    { label: 'Voice', ok: status.speech.configured, title: `${status.speech.model}, voice ${status.speech.voice}` },
    {
      label: status.dictionary.state === 'building' ? 'Dictionary (building)' : 'Dictionary',
      ok: status.dictionary.state === 'ready',
      title: status.dictionary.error ?? `Wiktionary: ${status.dictionary.state}`,
    },
    {
      label: 'Anki',
      ok: status.anki.ok && status.anki.sync === 'ok',
      title: status.anki.error ?? `anki-manager sync: ${status.anki.sync}`,
    },
  ]
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
      {items.map((i) => (
        <li key={i.label} title={i.title} className="flex items-center gap-1.5">
          <span aria-hidden className={`size-1.5 rounded-full ${i.ok ? 'bg-emerald-500' : 'bg-amber-500'}`} />
          {i.label}
          <span className="sr-only">{i.ok ? 'ready' : 'not ready'}</span>
        </li>
      ))}
    </ul>
  )
}
