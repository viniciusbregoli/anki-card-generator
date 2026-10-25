import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Copy, Info, Plus, Trash2 } from 'lucide-react'
import { api, type Check, type Draft, type DraftResult, type Example, type Kind } from '../api'
import {
  ARTICLE_SELECTED,
  ARTICLE_TEXT,
  ARTICLES,
  cardsFor,
  dictionaryLinks,
  KIND_LABELS,
  LANGUAGE_NAMES,
} from '../languages'
import { Button, Field, inputClass, PlayButton } from './ui'

// Examples mark the target word with <b>; while editing it shows as *word*.
const toEditable = (html: string) => html.replace(/<b>(.*?)<\/b>/g, '*$1*')
const fromEditable = (text: string) => text.replace(/\*([^*]+)\*/g, '<b>$1</b>')

export function headword(d: Draft) {
  return d.kind === 'noun' && d.article ? `${d.article} ${d.lemma}` : d.lemma
}

/** The value of a `prefix::value` tag, e.g. tagValue(tags, 'level') -> 'B1'. */
export const tagValue = (tags: string[], prefix: string) =>
  tags.find((t) => t.startsWith(`${prefix}::`))?.slice(prefix.length + 2) ?? ''

const withTag = (tags: string[], prefix: string, value: string) => [
  ...tags.filter((t) => !t.startsWith(`${prefix}::`)),
  ...(value ? [`${prefix}::${value}`] : []),
]

/** The editable body of one draft. */
export function DraftFields({
  result,
  draft,
  onChange,
}: {
  result: DraftResult
  draft: Draft
  onChange: (d: Draft) => void
}) {
  const status = useQuery({ queryKey: ['status'], queryFn: api.status })
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => onChange({ ...draft, [key]: value })
  const setExample = (i: number, patch: Partial<Example>) =>
    set(
      'examples',
      draft.examples.map((e, j) => (j === i ? { ...e, ...patch } : e)),
    )

  return (
    <div className="space-y-4">
      {result.input_note && (
        <p className="rounded-md bg-zinc-100 px-3 py-2 text-sm text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
          {result.input_note}
        </p>
      )}

      <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
        <Field label="Type">
          <select
            value={draft.kind}
            onChange={(e) => set('kind', e.target.value as Kind)}
            className={`${inputClass.replace('w-full ', '')} w-40`}
          >
            {(Object.entries(KIND_LABELS) as [Kind, string][]).map(([kind, label]) => (
              <option key={kind} value={kind}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <p className="pb-1.5 text-xs text-zinc-500 dark:text-zinc-400">
          Makes: {cardsFor(draft.kind, draft.language).join(' · ')}
        </p>
        {dictionaryLinks(draft).length > 0 && (
          <p className="ml-auto pb-1.5 text-xs text-zinc-500 dark:text-zinc-400">
            Look up:{' '}
            {dictionaryLinks(draft).map(([label, href], i) => (
              <span key={label}>
                {i > 0 && ' · '}
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-600 hover:underline dark:text-blue-400"
                >
                  {label}
                </a>
              </span>
            ))}
          </p>
        )}
      </div>

      {draft.kind === 'noun' && (
        <div className="grid gap-3 sm:grid-cols-[auto_1fr_1fr]">
          <Field label="Article">
            <div role="radiogroup" aria-label="Article" className="flex gap-1">
              {ARTICLES[draft.language].map((a, index) => (
                <button
                  key={a}
                  type="button"
                  role="radio"
                  aria-label={a}
                  aria-checked={draft.article === a}
                  tabIndex={draft.article === a || (!draft.article && index === 0) ? 0 : -1}
                  onClick={() => set('article', a)}
                  onKeyDown={(e) => {
                    const articles = ARTICLES[draft.language]
                    const index = articles.indexOf(a)
                    const next = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? (index + 1) % articles.length
                      : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? (index + articles.length - 1) % articles.length
                      : e.key === 'Home' ? 0 : e.key === 'End' ? articles.length - 1 : null
                    if (next === null) return
                    e.preventDefault()
                    set('article', articles[next])
                    e.currentTarget.parentElement?.querySelectorAll('button')[next]?.focus()
                  }}
                  className={`rounded-md px-3 py-1.5 text-sm font-semibold ring-1 transition-colors ${
                    draft.article === a
                      ? `${ARTICLE_SELECTED[a]} ring-transparent`
                      : `${ARTICLE_TEXT[a]} bg-white ring-zinc-200 hover:bg-zinc-50 dark:bg-zinc-900 dark:ring-zinc-800 dark:hover:bg-zinc-800`
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Noun">
            <input className={inputClass} value={draft.lemma} onChange={(e) => set('lemma', e.target.value)} />
          </Field>
          <Field label={draft.language === 'de' ? 'Plural (without die)' : 'Plural (without article)'}>
            <input className={inputClass} value={draft.plural} onChange={(e) => set('plural', e.target.value)} />
          </Field>
        </div>
      )}

      {draft.kind === 'verb' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Infinitive">
            <input className={inputClass} value={draft.lemma} onChange={(e) => set('lemma', e.target.value)} />
          </Field>
          <Field label={draft.language === 'de' ? 'Case or preposition' : 'Preposition'}>
            <input
              className={inputClass}
              value={draft.governs}
              placeholder={draft.language === 'de' ? 'auf + Akk.' : 'con + noun'}
              onChange={(e) => set('governs', e.target.value)}
            />
          </Field>
          {(['Present', 'Preterite', 'Perfect'] as const).map((label) => {
            const key = label.toLowerCase() as 'present' | 'preterite' | 'perfect'
            const person = draft.language === 'de' ? 'er/sie/es' : 'él/ella/usted'
            return (
              <Field key={key} label={`${label} (${person})`} className={key === 'perfect' ? 'sm:col-span-2' : ''}>
                <input className={inputClass} value={draft[key]} onChange={(e) => set(key, e.target.value)} />
              </Field>
            )
          })}
        </div>
      )}

      {draft.kind === 'word' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Word">
            <input className={inputClass} value={draft.lemma} onChange={(e) => set('lemma', e.target.value)} />
          </Field>
          <Field label="Part of speech">
            <input
              className={inputClass}
              value={draft.part_of_speech}
              onChange={(e) => set('part_of_speech', e.target.value)}
            />
          </Field>
        </div>
      )}

      {draft.kind === 'phrase' && (
        <Field label={LANGUAGE_NAMES[draft.language]}>
          <input className={inputClass} value={draft.lemma} onChange={(e) => set('lemma', e.target.value)} />
        </Field>
      )}

      <Field label={draft.kind === 'phrase' ? 'English' : 'Meaning'}>
        <input className={inputClass} value={draft.meaning} onChange={(e) => set('meaning', e.target.value)} />
      </Field>

      {draft.kind === 'noun' && (
        <Field label="Gender rule">
          <textarea
            rows={2}
            className={`${inputClass} resize-y`}
            value={draft.gender_rule}
            onChange={(e) => set('gender_rule', e.target.value)}
          />
        </Field>
      )}

      {draft.kind !== 'phrase' && (
        <fieldset className="space-y-2">
          <legend className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
            Examples <span className="font-normal">· *word* is shown in bold</span>
          </legend>
          {draft.examples.map((ex, i) => (
            <div key={i} className="flex items-start gap-1">
              <div className="grid min-w-0 flex-1 gap-1">
                <input
                  aria-label={`Example ${i + 1}, ${LANGUAGE_NAMES[draft.language]}`}
                  lang={draft.language}
                  className={inputClass}
                  value={toEditable(ex.de)}
                  onChange={(e) => setExample(i, { de: fromEditable(e.target.value) })}
                />
                <input
                  aria-label={`Example ${i + 1}, English`}
                  className={`${inputClass} text-zinc-600 dark:text-zinc-400`}
                  value={ex.en}
                  onChange={(e) => setExample(i, { en: e.target.value })}
                />
              </div>
              <PlayButton text={ex.de} language={draft.language} />
              <button
                type="button"
                aria-label={`Remove example ${i + 1}`}
                title="Remove example"
                onClick={() =>
                  set(
                    'examples',
                    draft.examples.filter((_, j) => j !== i),
                  )
                }
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
              >
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
          {draft.examples.length < 2 && (
            <Button variant="ghost" onClick={() => set('examples', [...draft.examples, { de: '', en: '' }])}>
              <Plus className="size-4" /> Add example
            </Button>
          )}
        </fieldset>
      )}

      <Field label="Note">
        <input className={inputClass} value={draft.note} onChange={(e) => set('note', e.target.value)} />
      </Field>

      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {(
          [
            ['level', 'Level', status.data?.tags.levels],
            ['topic', 'Topic', status.data?.tags.topics],
          ] as const
        ).map(([prefix, label, options]) => {
          const value = tagValue(draft.tags, prefix)
          return (
            <Field key={prefix} label={label}>
              <select
                value={value}
                onChange={(e) => set('tags', withTag(draft.tags, prefix, e.target.value))}
                className={`${inputClass.replace('w-full ', '')} w-40`}
              >
                <option value="">None</option>
                {/* Keep a value the list doesn't know, so editing never drops it silently. */}
                {[...(options ?? []), ...(value && !options?.includes(value) ? [value] : [])].map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </Field>
          )
        })}
      </div>

      <Checks checks={result.checks} />

      {result.duplicates.length > 0 && (
        <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900">
          <p className="flex items-center gap-1.5 font-medium">
            <Copy className="size-4" aria-hidden /> Already in your collection
          </p>
          <ul className="mt-1 space-y-0.5">
            {result.duplicates.map((d) => (
              <li key={d.id}>
                {d.text} <span className="text-amber-700 dark:text-amber-400">· {d.decks.join(', ')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Checks({ checks }: { checks: Check[] }) {
  if (!checks.length) return null
  const icon = {
    ok: <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-label="OK" />,
    warn: <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" aria-label="Warning" />,
    info: <Info className="mt-0.5 size-4 shrink-0 text-zinc-400" aria-label="Note" />,
  }
  return (
    <ul className="space-y-1 text-sm">
      {checks.map((c, i) => (
        <li key={i} className="flex items-start gap-2 text-zinc-700 dark:text-zinc-300">
          {icon[c.level]}
          <span className="text-pretty">{c.message}</span>
        </li>
      ))}
    </ul>
  )
}
