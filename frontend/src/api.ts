export type Language = 'de' | 'es'
export type Kind = 'noun' | 'verb' | 'word' | 'phrase'
export type Article = 'der' | 'die' | 'das' | 'el' | 'la' | 'los' | 'las' | ''

export interface Example {
  de: string
  en: string
}

export interface Draft {
  kind: Kind
  language: Language
  lemma: string
  article: Article
  plural: string
  part_of_speech: string
  meaning: string
  gender_rule: string
  present: string
  preterite: string
  perfect: string
  governs: string
  examples: Example[]
  note: string
  source: string
  /** level::B1, topic::food */
  tags: string[]
}

export interface Check {
  level: 'ok' | 'warn' | 'info'
  message: string
}

export interface Duplicate {
  id: number
  text: string
  notetype: string
  decks: string[]
}

export interface DraftResult {
  draft: Draft
  checks: Check[]
  input_note: string
  duplicates: Duplicate[]
}

export interface LanguageStatus {
  deck: string
  speech: { configured: boolean; model: string; voice: string }
  dictionary: { state: 'missing' | 'building' | 'ready' | 'error'; error: string | null }
}

export interface Status extends LanguageStatus {
  language: Language
  text_model: { configured: boolean; model: string }
  languages: Partial<Record<Language, LanguageStatus>>
  anki: { ok: boolean; sync: string | null; notes: number | null; error: string | null }
  tags: { levels: string[]; topics: string[] }
}

export interface RecentNote {
  id: number
  notetype: string
  first_field: string
  created: number
}

export class ApiError extends Error {
  status: number
  code?: string
  constructor(status: number, message: string, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { 'x-card-generator': '1' }
  if (body !== undefined) headers['content-type'] = 'application/json'
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!res.ok) {
    let message = res.statusText
    let code: string | undefined
    try {
      const data = await res.json()
      const detail = data.detail
      if (typeof detail === 'string') message = detail
      else if (detail?.message) message = detail.message
      else if (Array.isArray(detail)) message = detail.map((d) => d.msg).join('; ')
      code = data.code ?? detail?.code
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message, code ?? undefined)
  }
  return res.json() as Promise<T>
}

export const api = {
  status: () => request<Status>('GET', '/api/status'),
  draft: (body: { text: string; language: Language; context?: string; kind?: Kind | null }) =>
    request<DraftResult>('POST', '/api/drafts', body),
  speak: (text: string, language: Language) => request<{ url: string }>('POST', '/api/speak', { text, language }),
  save: (draft: Draft, allow_duplicate = false) =>
    request<{ id: number; notetype: string; deck: string; audio: number }>('POST', '/api/notes', {
      draft,
      allow_duplicate,
    }),
  recent: (language: Language) => request<RecentNote[]>('GET', `/api/recent?language=${language}`),
}
