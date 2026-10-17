"""Level and topic tags (`level::A1`, `topic::food`). The text model picks both while drafting."""

from __future__ import annotations

LEVELS = {
    "A1": "Beginner: the first few hundred everyday words (greetings, family, numbers, food, basic verbs).",
    "A2": "Elementary: common words for routine tasks, shopping, work, travel and simple descriptions.",
    "B1": "Intermediate: words for opinions, plans, experiences, work and the news in plain language.",
    "B2": "Upper intermediate: abstract, professional or specialised words met in newspapers and at work.",
    "C1": "Advanced: precise, formal or idiomatic vocabulary of educated speakers.",
    "C2": "Mastery: rare, literary, technical or regional words.",
}

TOPICS = {
    "people": "Family, friends, relationships, personal details, appearance.",
    "body-health": "The body, illness, doctors, medicine, hygiene.",
    "food": "Food, drink, cooking, meals, restaurants.",
    "home": "House, flat, rooms, furniture, household items and chores.",
    "clothes": "Clothing, shoes, accessories.",
    "shopping-money": "Shops, buying and selling, prices, money, banks.",
    "work": "Jobs, the workplace, companies, careers, applications.",
    "education": "School, university, courses, exams, learning.",
    "travel": "Transport, vehicles, trips, holidays, hotels, luggage.",
    "city": "Places and buildings in town, streets, directions, public services.",
    "nature": "Animals, plants, weather, seasons, landscape, environment.",
    "time": "Clock, dates, days, months, frequency, order of events.",
    "leisure": "Hobbies, sport, music, art, games, going out, celebrations.",
    "media": "Phone, internet, computers, TV, press, post and letters.",
    "feelings": "Emotions, moods, character traits, attitudes.",
    "conversation": "Greetings, politeness, opinions, agreeing, asking; verbs of saying and thinking.",
    "society": "Government, law, authorities and paperwork, politics, religion, history.",
    "qualities": "Colours, shapes, sizes, numbers, amounts, measures.",
    "grammar": "Function words: prepositions, conjunctions, pronouns, articles, particles, modal verbs.",
    "general": "Everyday or abstract words that fit none of the other topics.",
}


def prompt_text() -> str:
    """The prompt section that asks for both tags."""
    levels = "\n".join(f"  - {k}: {v}" for k, v in LEVELS.items())
    topics = "\n".join(f"  - {k}: {v}" for k, v in TOPICS.items())
    return (
        "- level: the CEFR level at which a learner usually meets this word or phrase, judged by how\n"
        f"common and basic it is:\n{levels}\n"
        f"- topic: the closest vocabulary topic:\n{topics}\n"
    )


def tags(level: str, topic: str) -> list[str]:
    return [t for t in (f"level::{level}" if level else "", f"topic::{topic}" if topic else "") if t]
