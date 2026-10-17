import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Copy, Info, Plus, Trash2 } from 'lucide-react'
import { api, type Article, type Check, type Draft, type DraftResult, type Example, type Kind } from '../api'
import { Button, Field, inputClass, PlayButton } from './ui'

export const KINDS: { value: Kind; label: string; cards: string[] }[] = [
  { value: 'noun', label: 'Noun', cards: ['German → English', 'English → German', 'Gender'] },
  { value: 'verb', label: 'Verb', cards: ['German → English', 'English → German'] },
  { value: 'word', label: 'Other word', cards: ['German → English', 'English → German'] },
  { value: 'phrase', label: 'Phrase', cards: ['German → English', 'English → German', 'Listening'] },
]

export const cardsFor = (kind: Kind) => KINDS.find((k) => k.value === kind)!.cards

export const ARTICLE_TEXT: Record<Exclude<Article, ''>, string> = {
  der: 'text-der',
  die: 'text-die',
  das: 'text-das',
}
const ARTICLE_SELECTED: Record<Exclude<Article, ''>, string> = {
  der: 'bg-der text-white',
  die: 'bg-die text-white',
  das: 'bg-das text-white',
}

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

/** Dictionary pages for the headword; the Anki cards get the same links (german.py). */
export function dictionaryLinks(d: Draft): [string, string][] {
  const full = d.lemma.replace(/<[^>]+>/g, '').trim()
  const w = full.replace(/^sich /, '')
  const vf = 'https://www.verbformen.com/'
  const enc = encodeURIComponent
  if (!full || d.kind === 'phrase') return []
  return [
    ['Wiktionary', `https://en.wiktionary.org/wiki/${enc(w.replace(/ /g, '_'))}#German`],
    ...(d.kind === 'verb' ? [['Conjugation', `${vf}conjugation/?w=${enc(full)}`] as [string, string]] : []),
    ...(d.kind === 'noun' ? [['Declension', `${vf}declension/nouns/?w=${enc(w)}`] as [string, string]] : []),
    ...(d.kind === 'word' && /adjecti/i.test(d.part_of_speech)
      ? [['Declension', `${vf}declension/adjectives/?w=${enc(w)}`] as [string, string]]
      : []),
    ['dict.cc', `https://www.dict.cc/?s=${enc(full)}`],
  ]
}

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
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </Field>
        <p className="pb-1.5 text-xs text-zinc-500 dark:text-zinc-400">Makes: {cardsFor(draft.kind).join(' · ')}</p>
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
              {(['der', 'die', 'das'] as const).map((a) => (
                <button
                  key={a}
                  type="button"
                  role="radio"
                  aria-checked={draft.article === a}
                  onClick={() => set('article', a)}
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
          <Field label="Plural (without die)">
            <input className={inputClass} value={draft.plural} onChange={(e) => set('plural', e.target.value)} />
          </Field>
        </div>
      )}

      {draft.kind === 'verb' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Infinitive">
            <input className={inputClass} value={draft.lemma} onChange={(e) => set('lemma', e.target.value)} />
          </Field>
          <Field label="Case or preposition">
            <input
              className={inputClass}
              value={draft.governs}
              placeholder="auf + Akk."
              onChange={(e) => set('governs', e.target.value)}
            />
          </Field>
          <Field label="Present (er/sie/es)">
            <input className={inputClass} value={draft.present} onChange={(e) => set('present', e.target.value)} />
          </Field>
          <Field label="Preterite (er/sie/es)">
            <input className={inputClass} value={draft.preterite} onChange={(e) => set('preterite', e.target.value)} />
          </Field>
          <Field label="Perfect (er/sie/es)" className="sm:col-span-2">
            <input className={inputClass} value={draft.perfect} onChange={(e) => set('perfect', e.target.value)} />
          </Field>
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
        <Field label="German">
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
                  aria-label={`Example ${i + 1}, German`}
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
              <PlayButton text={ex.de} />
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
