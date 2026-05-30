"""Rule-based topic scoring for zero-follower growth."""

from __future__ import annotations

import re

from app.discovery.schemas import TopicCandidate


GROWTH_WEIGHTS = {
    "visual_shock_score": 0.30,
    "curiosity_gap_score": 0.25,
    "dm_share_potential": 0.20,
    "watch_retention_potential": 0.15,
    "fact_safety_score": 0.10,
}

WHAT_IF_BOOST_TERMS = [
    "earth",
    "human",
    "humans",
    "body",
    "survival",
    "time",
    "gravity",
    "oxygen",
    "moon",
    "sun",
    "ocean",
    "oceans",
]
EXTREME_SCIENCE_BOOST_TERMS = [
    "planet",
    "star",
    "black hole",
    "gravity",
    "moon",
    "mars",
    "ocean",
    "storm",
    "time",
]
VISIBLE_CONSEQUENCE_TERMS = [
    "vanished",
    "disappeared",
    "stopped",
    "doubled",
    "exploded",
    "erupted",
    "rose",
    "flood",
    "freeze",
    "burn",
    "collapse",
    "fall",
    "dark",
    "tide",
    "storm",
    "crush",
    "rip",
    "tear",
    "blast",
]
VISUAL_TERMS = [
    "planet",
    "star",
    "black hole",
    "moon",
    "earth",
    "mars",
    "city",
    "cities",
    "ocean",
    "storm",
    "volcano",
    "meteor",
    "asteroid",
    "fire",
    "ice",
    "glass",
    "diamond",
    "rain",
    "sun",
    "gravity",
]
SHARE_TERMS = [
    "what if",
    "impossible",
    "extreme",
    "survival",
    "body",
    "earth",
    "moon",
    "sun",
    "black hole",
    "time",
    "humans",
]
ABSTRACT_TERMS = [
    "consciousness",
    "society",
    "ethics",
    "philosophy",
    "future of humanity",
    "innovation",
    "progress",
    "information",
    "systems",
    "framework",
]
TECHNICAL_TERMS = [
    "spectroscopy",
    "isotope",
    "quantum field",
    "methodology",
    "taxonomy",
    "regression",
    "statistical",
    "molecular",
    "algorithmic",
    "cryovolcanism",
    "magnetohydrodynamics",
]
CONTROVERSY_TERMS = [
    "election",
    "president",
    "war crime",
    "lawsuit",
    "vaccine",
    "diagnosis",
    "treatment",
    "conspiracy",
    "hoax",
    "propaganda",
]
LONG_EXPLANATION_TERMS = [
    "history of",
    "overview",
    "everything about",
    "complete guide",
    "explained fully",
    "policy",
    "economics",
    "supply chain",
]
WEAK_IMAGE_TERMS = [
    "data",
    "software",
    "privacy",
    "policy",
    "statistics",
    "language model",
    "market",
    "productivity",
]


def score_candidate(candidate: TopicCandidate) -> TopicCandidate:
    text = _candidate_text(candidate)
    lane = candidate.lane

    visual_shock_score = _visual_shock_score(text, lane)
    curiosity_gap_score = _curiosity_gap_score(candidate.topic, text, lane)
    dm_share_potential = _dm_share_potential(text, lane)
    watch_retention_potential = _watch_retention_potential(candidate.topic, text, lane)
    fact_safety_score = _fact_safety_score(text, candidate.source)
    cold_audience_fit = _cold_audience_fit(candidate.topic, text, lane)
    first_second_clarity = _first_second_clarity(candidate.topic, text)

    penalties = _penalty_total(candidate.topic, text, candidate.source)
    breakdown = {
        "visual_shock_score": visual_shock_score,
        "curiosity_gap_score": curiosity_gap_score,
        "dm_share_potential": dm_share_potential,
        "watch_retention_potential": watch_retention_potential,
        "fact_safety_score": fact_safety_score,
        "penalties": penalties,
    }
    score = sum(breakdown[key] * weight for key, weight in GROWTH_WEIGHTS.items()) - penalties

    reasons = list(candidate.reasons)
    warnings = list(candidate.warnings)

    if lane == "what_if_disaster" and candidate.topic.lower().startswith("what if"):
        reasons.append("Starts with a clear what-if hook for cold audiences.")
    if lane == "what_if_disaster" and _count_terms(text, WHAT_IF_BOOST_TERMS) >= 2:
        reasons.append("Affects familiar survival-scale forces like Earth, humans, gravity, oxygen, moon, sun, or ocean.")
    if lane == "extreme_science" and _count_terms(text, EXTREME_SCIENCE_BOOST_TERMS) >= 2:
        reasons.append("Uses impossible-feeling science with strong visual anchors.")
    if visual_shock_score >= 78:
        reasons.append("High AI-image potential with immediate visual shock.")
    if curiosity_gap_score >= 78:
        reasons.append("Strong curiosity gap for non-followers.")
    if dm_share_potential >= 76:
        reasons.append("Feels like a DM-share prompt: quick, strange, and easy to send.")
    if watch_retention_potential >= 76:
        reasons.append("Can unfold as a short consequence chain in 5 slides or 8-12 seconds.")

    if _count_terms(text, ABSTRACT_TERMS):
        warnings.append("Abstract topic; make the consequence visible immediately.")
    if _count_terms(text, TECHNICAL_TERMS):
        warnings.append("May be too technical for a cold audience unless simplified.")
    if _count_terms(text, CONTROVERSY_TERMS):
        warnings.append("Politics/current or sensitive topic; use only when source-backed and carefully framed.")
    if _count_terms(text, WEAK_IMAGE_TERMS):
        warnings.append("Weak AI-image potential; needs a stronger visual metaphor.")
    if _needs_long_explanation(candidate.topic, text):
        warnings.append("May need too much explanation for 5 slides or an 8-12 second Reel.")

    return candidate.model_copy(
        update={
            "visual_shock_score": round(visual_shock_score, 2),
            "curiosity_gap_score": round(curiosity_gap_score, 2),
            "dm_share_potential": round(dm_share_potential, 2),
            "watch_retention_potential": round(watch_retention_potential, 2),
            "cold_audience_fit": round(cold_audience_fit, 2),
            "first_second_clarity": round(first_second_clarity, 2),
            "score": round(_clamp(score), 2),
            "score_breakdown": {key: round(value, 2) for key, value in breakdown.items()},
            "reasons": _unique(reasons),
            "warnings": _unique(warnings),
        }
    )


def score_candidates(candidates: list[TopicCandidate]) -> list[TopicCandidate]:
    return [score_candidate(candidate) for candidate in candidates]


def _visual_shock_score(text: str, lane: str) -> float:
    score = 38 + _count_terms(text, VISUAL_TERMS) * 7 + _count_terms(text, VISIBLE_CONSEQUENCE_TERMS) * 6
    if lane == "what_if_disaster":
        score += _count_terms(text, WHAT_IF_BOOST_TERMS) * 4
    if lane == "extreme_science":
        score += _count_terms(text, EXTREME_SCIENCE_BOOST_TERMS) * 5
        if _term_in_text(text, "impossible") or _term_in_text(text, "extreme"):
            score += 8
    if _count_terms(text, WEAK_IMAGE_TERMS):
        score -= 18
    return _clamp(score)


def _curiosity_gap_score(topic: str, text: str, lane: str) -> float:
    score = 42 + _count_terms(text, SHARE_TERMS) * 6
    if topic.lower().startswith("what if"):
        score += 18
    if lane == "extreme_science" and any(
        phrase in text for phrase in ("so dense", "darker than", "diamond rain", "without a star", "time runs")
    ):
        score += 14
    if "?" in topic:
        score += 4
    if _count_terms(text, ABSTRACT_TERMS):
        score -= 16
    return _clamp(score)


def _dm_share_potential(text: str, lane: str) -> float:
    score = 36 + _count_terms(text, SHARE_TERMS) * 6 + _count_terms(text, VISIBLE_CONSEQUENCE_TERMS) * 4
    if lane == "what_if_disaster":
        score += 12
    if lane == "future_scenario" and any(term in text for term in ("ai", "robot", "doctor", "school", "driver")):
        score += 9
    if _count_terms(text, TECHNICAL_TERMS):
        score -= 12
    return _clamp(score)


def _watch_retention_potential(topic: str, text: str, lane: str) -> float:
    score = 45
    if _has_immediate_consequence(text):
        score += 18
    if _can_fit_short(topic, text):
        score += 16
    if lane in {"what_if_disaster", "future_scenario"} and topic.lower().startswith("what if"):
        score += 8
    if _needs_long_explanation(topic, text):
        score -= 22
    return _clamp(score)


def _fact_safety_score(text: str, source: str) -> float:
    score = 78
    if source in {"nasa", "wikipedia"}:
        score += 10
    if source == "gdelt":
        score += 2
    if any(phrase in text for phrase in ("what if", "future", "scenario")):
        score -= 4
    score -= _count_terms(text, CONTROVERSY_TERMS) * 18
    if "conspiracy" in text or "hoax" in text:
        score -= 25
    return _clamp(score)


def _cold_audience_fit(topic: str, text: str, lane: str) -> float:
    score = 50
    if len(topic.split()) <= 9:
        score += 12
    if _count_terms(text, SHARE_TERMS):
        score += 14
    if lane != "any":
        score += 8
    if _count_terms(text, ABSTRACT_TERMS + TECHNICAL_TERMS):
        score -= 18
    return _clamp(score)


def _first_second_clarity(topic: str, text: str) -> float:
    score = 48
    words = len(re.findall(r"[A-Za-z0-9]+", topic))
    if 4 <= words <= 10:
        score += 18
    if topic.lower().startswith("what if"):
        score += 18
    if _count_terms(text, VISUAL_TERMS):
        score += 8
    if words > 13:
        score -= (words - 13) * 5
    if _count_terms(text, TECHNICAL_TERMS):
        score -= 16
    return _clamp(score)


def _candidate_text(candidate: TopicCandidate) -> str:
    parts = [
        candidate.topic,
        candidate.lane,
        candidate.angle,
        candidate.source_title or "",
        candidate.source_summary or "",
        " ".join(candidate.keywords),
    ]
    return " ".join(parts).lower()


def _penalty_total(topic: str, text: str, source: str) -> float:
    penalty = 0.0
    penalty += _count_terms(text, ABSTRACT_TERMS) * 5
    penalty += _count_terms(text, TECHNICAL_TERMS) * 6
    penalty += _count_terms(text, WEAK_IMAGE_TERMS) * 5
    if _needs_long_explanation(topic, text):
        penalty += 8
    if _count_terms(text, CONTROVERSY_TERMS) and source not in {"nasa", "wikipedia", "gdelt"}:
        penalty += 14
    return _clamp(penalty, high=35)


def _has_immediate_consequence(text: str) -> bool:
    return _count_terms(text, VISIBLE_CONSEQUENCE_TERMS) > 0


def _can_fit_short(topic: str, text: str) -> bool:
    return len(topic.split()) <= 10 and not _count_terms(text, TECHNICAL_TERMS + LONG_EXPLANATION_TERMS)


def _needs_long_explanation(topic: str, text: str) -> bool:
    return len(topic.split()) > 13 or _count_terms(text, LONG_EXPLANATION_TERMS) > 0


def _count_terms(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if _term_in_text(text, term))


def _term_in_text(text: str, term: str) -> bool:
    normalized = term.lower()
    if re.fullmatch(r"[a-z0-9]+", normalized):
        return re.search(rf"\b{re.escape(normalized)}\b", text) is not None
    return normalized in text


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique
