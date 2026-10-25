import type { Article, Draft, Kind, Language } from './api'

export const LANGUAGE_NAMES: Record<Language, string> = { de: 'German', es: 'Spanish' }
export const PLACEHOLDERS: Record<Language, string> = { de: 'Rechnung', es: 'factura' }

export const KIND_LABELS: Record<Kind, string> = {
  noun: 'Noun',
  verb: 'Verb',
  word: 'Other word',
  phrase: 'Phrase',
}

export function cardsFor(kind: Kind, language: Language = 'de') {
  const name = LANGUAGE_NAMES[language]
  const cards = [`${name} → English`, `English → ${name}`]
  if (kind === 'noun') cards.push('Gender')
  if (kind === 'phrase') cards.push('Listening')
  return cards
}

export type NounArticle = Exclude<Article, ''>

export const ARTICLES: Record<Language, NounArticle[]> = {
  de: ['der', 'die', 'das'],
  es: ['el', 'la', 'los', 'las'],
}

export const ARTICLE_TEXT: Record<NounArticle, string> = {
  der: 'text-der',
  die: 'text-die',
  das: 'text-das',
  el: 'text-el',
  la: 'text-la',
  los: 'text-los',
  las: 'text-las',
}

export const ARTICLE_SELECTED: Record<NounArticle, string> = {
  der: 'bg-der text-white',
  die: 'bg-die text-white',
  das: 'bg-das text-white',
  el: 'bg-el text-white',
  la: 'bg-la text-white',
  los: 'bg-los text-white',
  las: 'bg-las text-white',
}

export function dictionaryLinks(d: Draft): [string, string][] {
  const full = d.lemma.replace(/<[^>]+>/g, '').trim()
  const enc = encodeURIComponent
  if (!full || d.kind === 'phrase') return []
  if (d.language === 'es') {
    const w = d.kind === 'verb' ? full.replace(/se$/, '') : full
    return [
      ['Wiktionary', `https://en.wiktionary.org/wiki/${enc(w.replace(/ /g, '_'))}#Spanish`],
      ...(d.kind === 'verb'
        ? [['Conjugation', `https://www.wordreference.com/conj/esverbs.aspx?v=${enc(w)}`] as [string, string]]
        : []),
      ['Spanish-English', `https://www.wordreference.com/es/en/translation.asp?spen=${enc(w)}`],
    ]
  }
  const w = full.replace(/^sich /, '')
  const vf = 'https://www.verbformen.com/'
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
