"""Carousel planning orchestration."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.content.plan_scorer import score_plan
from app.content.schemas import (
    CAPTION_HARD_MIN_WORDS,
    CAPTION_TARGET_MAX_WORDS,
    CAPTION_TARGET_MIN_WORDS,
    CarouselPlan,
    count_words,
)
from app.llm.base import LLMProvider
from app.llm.prompt_templates import (
    build_caption_retry_prompt,
    build_carousel_prompt,
    build_quality_retry_prompt,
    build_repair_prompt,
)


logger = logging.getLogger(__name__)

WEAK_PHRASES = (
    "beneath the surface",
    "crowded reality",
    "hidden lives",
    "hidden truth",
    "rome's glory",
    "social hierarchy",
    "simple life",
    "sharp contrasts",
    "city of contrasts",
    "roman shadows",
    "secrets and scandals",
    "a hidden truth",
    "dirty secret",
    "uncover",
    "what was life like",
    "discover the secrets",
    "discover",
    "explore",
    "share your thoughts",
    "a day in the life",
    "from dawn till dusk",
    "secrets of a bygone era",
    "learn more",
    "save for more",
    "follow for more",
    "follow for",
    "latest science updates",
    "prepare for the unexpected",
    "new ecosystems",
    "before the flood",
    "uncover more",
    "click to",
    "you won't believe",
    "mind-blowing",
    "blow your mind",
)

ABSTRACT_HEADLINE_LABELS = {
    "beneath the surface",
    "crowded reality",
    "hidden lives",
    "social hierarchy",
    "city of contrasts",
    "roman shadows",
    "roman life",
    "roman society",
    "romes glory",
    "simple life",
    "sharp contrasts",
    "survive rome",
    "hidden truth",
    "a hidden truth",
    "secrets and scandals",
    "wealth and poverty",
}

SCIENCE_UNCERTAINTY_MARKERS = (
    "may",
    "could",
    "might",
    "scientists think",
    "researchers suggest",
    "one possible explanation",
    "appears to",
    "is thought to",
)

FUTURE_SPECULATION_MARKERS = (
    "what if",
    "could",
    "might",
    "may",
    "in this scenario",
    "speculative",
    "possibility",
)

IMPORTANT_KEYWORD_STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "almost",
    "along",
    "also",
    "another",
    "because",
    "before",
    "being",
    "between",
    "beyond",
    "could",
    "every",
    "first",
    "from",
    "have",
    "into",
    "just",
    "like",
    "many",
    "more",
    "much",
    "must",
    "other",
    "post",
    "same",
    "should",
    "slide",
    "some",
    "that",
    "their",
    "there",
    "these",
    "this",
    "through",
    "with",
    "would",
    "your",
}

NEUTRON_STAR_TOPIC_MARKERS = (
    "neutron star",
    "dense star",
    "spoonful weighs",
    "spoonful",
    "teaspoon",
    "sugar cube",
    "billions of tons",
    "collapsed star",
)

NEUTRON_STAR_OFF_TOPIC_CONCEPTS = (
    "exoplanet weather",
    "glass rain",
    "alien atmosphere",
    "alien weather",
    "worlds beyond earth with weather",
    "worlds beyond earth",
    "distant planet",
)

SCIENCE_WEATHER_TOPIC_MARKERS = (
    "exoplanet",
    "glass rain",
    "alien weather",
    "alien atmosphere",
    "planet where it may rain glass",
    "worlds beyond earth",
)

DISASTER_TOPIC_MARKERS = (
    "what if",
    "ocean",
    "oceans",
    "flood",
    "flooded",
    "rose overnight",
    "disaster",
)


class CarouselPlanningError(RuntimeError):
    """Raised when a valid carousel plan cannot be produced."""


@dataclass
class PlanningRunInfo:
    llm_provider_used: str = ""
    llm_model_used: str = ""
    llm_fallback_attempts: list[dict[str, str]] = field(default_factory=list)
    llm_failures: list[dict[str, str]] = field(default_factory=list)
    compare_plans_used: bool = False
    candidate_plan_scores: dict[str, dict[str, object]] = field(default_factory=dict)
    caption_quality_warnings: list[str] = field(default_factory=list)
    caption_regenerated: bool = False
    caption_alignment_score: int = 0


@dataclass(frozen=True)
class CaptionAlignmentReport:
    score: int
    matched_keywords: list[str]
    unrelated_concepts: list[str]
    warnings: list[str]


def strip_json_fences(raw: str) -> str:
    text = raw.strip()
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    return text


def parse_carousel_plan(raw: str) -> CarouselPlan:
    text = strip_json_fences(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CarouselPlanningError(f"Invalid JSON: {exc}") from exc

    try:
        return CarouselPlan.model_validate(payload)
    except ValidationError as exc:
        raise CarouselPlanningError(str(exc)) from exc


class CarouselPlanner:
    def __init__(self, providers: LLMProvider | Sequence[LLMProvider], compare_plans: bool = False) -> None:
        if isinstance(providers, LLMProvider):
            self.providers = [providers]
        else:
            self.providers = list(providers)
        if not self.providers:
            raise CarouselPlanningError("No LLM providers are configured.")
        self.compare_plans = compare_plans
        self.last_run_info = PlanningRunInfo(compare_plans_used=compare_plans)

    def plan(
        self,
        topic: str,
        niche: str,
        slide_count: int,
        template: str,
        debug_dir: Path,
        research_context: str = "",
        content_patterns: str = "",
        discovery_angle: str = "",
    ) -> CarouselPlan:
        prompt = build_carousel_prompt(
            topic=topic,
            niche=niche,
            slides=slide_count,
            template=template,
            research_context=research_context,
            content_patterns=content_patterns,
            discovery_angle=discovery_angle,
        )
        if self.compare_plans:
            return self._plan_with_comparison(prompt=prompt, debug_dir=debug_dir, discovery_angle=discovery_angle)
        return self._plan_with_fallback(prompt=prompt, debug_dir=debug_dir, discovery_angle=discovery_angle)

    def _plan_with_fallback(self, prompt: str, debug_dir: Path, discovery_angle: str = "") -> CarouselPlan:
        self.last_run_info = PlanningRunInfo(compare_plans_used=False)
        for provider in self.providers:
            self.last_run_info.llm_fallback_attempts.append(
                {"provider": provider.name, "model": provider.model}
            )
            try:
                plan = self._plan_with_provider(
                    provider=provider,
                    prompt=prompt,
                    debug_dir=debug_dir,
                    discovery_angle=discovery_angle,
                )
            except Exception as exc:
                reason = str(exc)
                self.last_run_info.llm_failures.append(
                    {"provider": provider.name, "model": provider.model, "reason": reason}
                )
                logger.warning("LLM provider %s failed; trying next provider. Reason: %s", provider.name, reason)
                continue

            self.last_run_info.llm_provider_used = provider.name
            self.last_run_info.llm_model_used = provider.model
            return plan

        failure_summary = "; ".join(
            f"{item['provider']} ({item['model']}): {item['reason']}"
            for item in self.last_run_info.llm_failures
        )
        raise CarouselPlanningError(
            "All configured LLM providers failed. Check API keys, rate limits, and model names. "
            "If this project later adds --use-last-plan or --mock-plan, use one of those to continue locally. "
            f"Failures: {failure_summary}"
        )

    def _plan_with_comparison(self, prompt: str, debug_dir: Path, discovery_angle: str = "") -> CarouselPlan:
        self.last_run_info = PlanningRunInfo(compare_plans_used=True)
        candidate_root = debug_dir / "candidate_plans"
        candidate_root.mkdir(parents=True, exist_ok=True)
        candidates: list[tuple[int, LLMProvider, CarouselPlan]] = []
        candidate_caption_regenerated: dict[str, bool] = {}

        for provider in self.providers:
            self.last_run_info.llm_fallback_attempts.append(
                {"provider": provider.name, "model": provider.model}
            )
            previous_caption_regenerated = self.last_run_info.caption_regenerated
            self.last_run_info.caption_regenerated = False
            try:
                plan = self._plan_with_provider(
                    provider=provider,
                    prompt=prompt,
                    debug_dir=candidate_root / provider.name,
                    discovery_angle=discovery_angle,
                )
                provider_caption_regenerated = self.last_run_info.caption_regenerated
            except Exception as exc:
                self.last_run_info.caption_regenerated = previous_caption_regenerated
                reason = str(exc)
                self.last_run_info.llm_failures.append(
                    {"provider": provider.name, "model": provider.model, "reason": reason}
                )
                logger.warning("LLM candidate from %s failed validation. Reason: %s", provider.name, reason)
                continue
            self.last_run_info.caption_regenerated = previous_caption_regenerated or provider_caption_regenerated

            (candidate_root / f"{provider.name}_plan.json").write_text(
                plan.model_dump_json(indent=2),
                encoding="utf-8",
            )
            plan_score = score_plan(plan)
            candidate_caption_regenerated[provider.name] = provider_caption_regenerated
            self.last_run_info.candidate_plan_scores[provider.name] = {
                "provider": provider.name,
                "model": provider.model,
                **plan_score.as_dict(),
            }
            candidates.append((plan_score.score, provider, plan))

        if self.last_run_info.candidate_plan_scores:
            (candidate_root / "plan_scores.json").write_text(
                json.dumps(self.last_run_info.candidate_plan_scores, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if not candidates:
            failure_summary = "; ".join(
                f"{item['provider']} ({item['model']}): {item['reason']}"
                for item in self.last_run_info.llm_failures
            )
            raise CarouselPlanningError(
                "Compare mode could not produce a valid plan from any available provider. "
                "Check API keys, rate limits, and model names. "
                f"Failures: {failure_summary}"
            )

        _score, provider, plan = max(candidates, key=lambda item: item[0])
        self.last_run_info.llm_provider_used = provider.name
        self.last_run_info.llm_model_used = provider.model
        self.last_run_info.caption_regenerated = False
        self._record_caption_quality(
            plan,
            regenerated=candidate_caption_regenerated.get(provider.name, False),
            discovery_angle=discovery_angle,
        )
        return plan

    def _plan_with_provider(
        self,
        provider: LLMProvider,
        prompt: str,
        debug_dir: Path,
        discovery_angle: str = "",
    ) -> CarouselPlan:
        plan = self._generate_valid_plan(
            provider=provider,
            prompt=prompt,
            debug_dir=debug_dir,
            attempt_prefix="attempt",
        )
        quality_issues = find_quality_issues(plan, discovery_angle=discovery_angle)
        if not quality_issues:
            self._record_caption_quality(plan, regenerated=False, discovery_angle=discovery_angle)
            return plan

        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "llm_weak_response_attempt_1.json").write_text(
            plan.model_dump_json(indent=2),
            encoding="utf-8",
        )
        if all(is_caption_quality_issue(issue) for issue in quality_issues):
            return self._repair_caption_if_needed(provider, plan, debug_dir, discovery_angle=discovery_angle)

        quality_prompt = build_quality_retry_prompt(
            original_prompt=prompt,
            valid_response=plan.model_dump_json(indent=2),
            issues=quality_issues,
        )
        try:
            retry_plan = self._generate_valid_plan(
                provider=provider,
                prompt=quality_prompt,
                debug_dir=debug_dir,
                attempt_prefix="quality_retry",
            )
            return self._repair_caption_if_needed(
                provider,
                retry_plan,
                debug_dir,
                discovery_angle=discovery_angle,
            )
        except CarouselPlanningError as exc:
            (debug_dir / "llm_quality_retry_failed.txt").write_text(str(exc), encoding="utf-8")
            self._record_caption_quality(plan, regenerated=False, discovery_angle=discovery_angle)
            return plan

    def _generate_valid_plan(
        self,
        provider: LLMProvider,
        prompt: str,
        debug_dir: Path,
        attempt_prefix: str,
    ) -> CarouselPlan:
        raw = provider.generate_json(prompt)
        try:
            return parse_carousel_plan(raw)
        except CarouselPlanningError as first_error:
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"llm_failed_response_{attempt_prefix}_1.txt").write_text(raw, encoding="utf-8")
            repair_prompt = build_repair_prompt(prompt, raw, str(first_error))
            repaired = provider.generate_json(repair_prompt)
            try:
                return parse_carousel_plan(repaired)
            except CarouselPlanningError as second_error:
                (debug_dir / f"llm_failed_response_{attempt_prefix}_2.txt").write_text(
                    repaired,
                    encoding="utf-8",
                )
                raise CarouselPlanningError(
                    f"Could not create a valid carousel plan after retry: {second_error}"
                ) from second_error

    def _repair_caption_if_needed(
        self,
        provider: LLMProvider,
        plan: CarouselPlan,
        debug_dir: Path,
        discovery_angle: str = "",
    ) -> CarouselPlan:
        caption_issues = find_caption_quality_issues(plan, discovery_angle=discovery_angle)
        if not caption_issues:
            self._record_caption_quality(plan, regenerated=False, discovery_angle=discovery_angle)
            return plan

        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "caption_weak_after_quality_retry.txt").write_text(
            "\n".join(caption_issues),
            encoding="utf-8",
        )
        prompt = build_caption_retry_prompt(
            valid_response=plan.model_dump_json(indent=2),
            issues=caption_issues,
            discovery_angle=discovery_angle,
        )
        try:
            raw = provider.generate_json(prompt)
        except Exception as exc:
            fallback = plan.model_copy(update={"caption": build_rule_based_caption(plan)})
            remaining_issues = find_caption_quality_issues(fallback, discovery_angle=discovery_angle)
            if not remaining_issues:
                (debug_dir / "caption_retry_failed_response.txt").write_text(str(exc), encoding="utf-8")
                (debug_dir / "caption_rule_based_fallback.txt").write_text(
                    fallback.caption,
                    encoding="utf-8",
                )
                self._record_caption_quality(fallback, regenerated=True, discovery_angle=discovery_angle)
                return fallback
            raise

        try:
            payload = json.loads(strip_json_fences(raw))
            caption = str(payload["caption"]).strip()
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            (debug_dir / "caption_retry_failed_response.txt").write_text(raw, encoding="utf-8")
            raise CarouselPlanningError(f"Caption retry returned invalid JSON: {exc}") from exc

        candidate = plan.model_copy(update={"caption": caption})
        remaining_issues = find_caption_quality_issues(candidate, discovery_angle=discovery_angle)
        if remaining_issues:
            (debug_dir / "caption_retry_failed_response.txt").write_text(raw, encoding="utf-8")
            fallback = plan.model_copy(update={"caption": build_rule_based_caption(plan)})
            fallback_issues = find_caption_quality_issues(fallback, discovery_angle=discovery_angle)
            if fallback_issues:
                raise CarouselPlanningError(
                    "Caption retry did not meet quality rules: " + "; ".join(remaining_issues)
                )
            (debug_dir / "caption_rule_based_fallback.txt").write_text(
                fallback.caption,
                encoding="utf-8",
            )
            self._record_caption_quality(fallback, regenerated=True, discovery_angle=discovery_angle)
            return fallback

        (debug_dir / "caption_retry_response.json").write_text(
            json.dumps({"caption": caption}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._record_caption_quality(candidate, regenerated=True, discovery_angle=discovery_angle)
        return candidate

    def _record_caption_quality(
        self,
        plan: CarouselPlan,
        regenerated: bool,
        discovery_angle: str = "",
    ) -> None:
        report = build_caption_alignment_report(plan, discovery_angle=discovery_angle)
        self.last_run_info.caption_quality_warnings = find_caption_quality_issues(
            plan,
            discovery_angle=discovery_angle,
        )
        self.last_run_info.caption_alignment_score = report.score
        self.last_run_info.caption_regenerated = self.last_run_info.caption_regenerated or regenerated


def find_quality_issues(plan: CarouselPlan, discovery_angle: str = "") -> list[str]:
    issues: list[str] = []
    if is_missing_or_placeholder(plan.selected_pattern):
        issues.append("selected_pattern is missing or placeholder-like.")

    if is_vague_content_angle(plan.content_angle):
        issues.append("content_angle is too vague; make it concrete and tied to the topic.")

    for field_name in ("title", "selected_pattern", "content_angle", "caption"):
        value = getattr(plan, field_name)
        phrase = find_weak_phrase(value)
        if phrase:
            issues.append(f"{field_name} contains weak phrase: {phrase!r}.")

    issues.extend(find_caption_quality_issues(plan, discovery_angle=discovery_angle))

    for slide in plan.slides:
        for field_name in ("headline", "subtext"):
            value = getattr(slide, field_name)
            phrase = find_weak_phrase(value)
            if phrase:
                issues.append(
                    f"Slide {slide.slide_number} {field_name} contains weak phrase: {phrase!r}."
                )

    if is_what_if_disaster_plan(plan):
        issues.extend(find_disaster_structure_issues(plan))

    if plan.slides:
        first = plan.slides[0]
        if first.headline.strip().lower().startswith(("what is", "what are", "what was", "what were")):
            issues.append("Slide 1 reads like a generic educational question instead of a cover hook.")
        if is_abstract_headline(first.headline):
            issues.append("Slide 1 headline is vague or abstract; make it a concrete cover hook.")

        abstract_count = sum(1 for slide in plan.slides if is_abstract_headline(slide.headline))
        if abstract_count > 2:
            issues.append("More than 2 slide headlines are abstract labels instead of concrete moments.")

        final = plan.slides[-1]
        if final.role in {"CTA", "final"} and not any(
            marker in f"{final.headline} {final.subtext}".lower()
            for marker in ("save", "comment", "follow", "would you", "could you", "part 2", "send this")
        ):
            issues.append("Final slide CTA is not specific enough for comments, saves, or follows.")

    return issues


def is_what_if_disaster_plan(plan: CarouselPlan) -> bool:
    text = normalize_for_quality(
        " ".join(
            [
                plan.topic,
                plan.content_angle,
                plan.title,
                " ".join(slide.headline for slide in plan.slides),
                " ".join(slide.visual_goal for slide in plan.slides),
            ]
        )
    )
    return ("what if" in text or "overnight" in text) and any(marker in text for marker in DISASTER_TOPIC_MARKERS)


def find_disaster_structure_issues(plan: CarouselPlan) -> list[str]:
    issues: list[str] = []
    slide_text = [normalize_for_quality(f"{slide.headline} {slide.subtext} {slide.visual_goal}") for slide in plan.slides]
    required_markers = [
        ("cover hook", ("ocean", "water", "moves", "overnight", "warning")),
        ("street consequence", ("street", "road", "river", "cars")),
        ("human utility consequence", ("power", "dark", "lights", "fails")),
        ("hidden water consequence", ("clean water", "drinking", "water", "tap", "infrastructure")),
        ("survival question", ("where", "go", "survive", "?")),
    ]
    for index, (label, markers) in enumerate(required_markers):
        if index >= len(slide_text):
            break
        haystack = slide_text[index]
        if not any(marker.replace(" ", "") in haystack.replace(" ", "") for marker in markers):
            issues.append(f"What-if disaster slide {index + 1} needs a sharper {label} beat.")

    generic = ("millions displaced", "nature adapts", "new ecosystem", "prepare for unexpected")
    if any(any(phrase in text for phrase in generic) for text in slide_text):
        issues.append("What-if disaster slides contain generic or weak consequence wording.")
    return issues


def is_caption_quality_issue(issue: str) -> bool:
    return issue.lower().startswith("caption ")


def find_caption_quality_issues(plan: CarouselPlan, discovery_angle: str = "") -> list[str]:
    caption = plan.caption.strip()
    lower_caption = caption.lower()
    word_count = count_words(caption)
    issues: list[str] = []
    weak_phrase = find_weak_phrase(caption)

    if weak_phrase:
        issues.append(f"caption contains weak phrase: {weak_phrase!r}.")

    if word_count < CAPTION_HARD_MIN_WORDS:
        issues.append(
            f"caption is too short at {word_count} words; captions under "
            f"{CAPTION_HARD_MIN_WORDS} words are weak."
        )
    elif word_count < CAPTION_TARGET_MIN_WORDS or word_count > CAPTION_TARGET_MAX_WORDS:
        issues.append(
            f"caption is {word_count} words; target a story-style caption of "
            f"{CAPTION_TARGET_MIN_WORDS}-{CAPTION_TARGET_MAX_WORDS} words."
        )

    if "\n" not in caption:
        issues.append("caption needs short paragraph line breaks.")

    if "?" not in caption:
        issues.append("caption needs one natural question CTA.")

    if not any(marker in lower_caption for marker in ("save", "follow")):
        issues.append("caption needs one natural save or follow CTA.")

    if "#" in caption:
        issues.append("caption contains hashtags; keep hashtags only in hashtags.txt/hashtags array.")

    niche = normalize_for_quality(plan.niche)
    if niche == "science" and not any(marker in lower_caption for marker in SCIENCE_UNCERTAINTY_MARKERS):
        issues.append(
            "science caption needs careful uncertainty language such as may, could, "
            "scientists think, researchers suggest, or one possible explanation."
        )

    if niche == "future" and not any(marker in lower_caption for marker in FUTURE_SPECULATION_MARKERS):
        issues.append(
            "future caption needs speculative framing such as what if, could, might, "
            "or in this scenario."
        )

    alignment = build_caption_alignment_report(plan, discovery_angle=discovery_angle)
    issues.extend(alignment.warnings)

    return issues


def build_caption_alignment_report(plan: CarouselPlan, discovery_angle: str = "") -> CaptionAlignmentReport:
    grounding_text = build_caption_grounding_text(plan, discovery_angle=discovery_angle)
    caption_text = normalize_for_quality(plan.caption)
    keywords = extract_important_caption_keywords(plan)
    caption_tokens = {normalize_keyword(token) for token in re.findall(r"[a-z0-9]+", caption_text)}
    matched_keywords = sorted(keyword for keyword in keywords if normalize_keyword(keyword) in caption_tokens)

    unrelated_concepts = find_unrelated_caption_concepts(
        plan=plan,
        caption_text=caption_text,
        grounding_text=normalize_for_quality(grounding_text),
    )
    overlap_score = min(80, len(matched_keywords) * 25)
    score = max(0, min(100, overlap_score + 20 - (len(unrelated_concepts) * 35)))
    warnings: list[str] = []

    if len(matched_keywords) < 2:
        warnings.append(
            "caption alignment is too low; caption must include at least 2 important "
            "keywords from the topic, content_angle, slide headlines, or fact_claims."
        )

    if unrelated_concepts:
        warnings.append(
            "caption mentions unrelated concepts for this topic: " + ", ".join(unrelated_concepts) + "."
        )

    return CaptionAlignmentReport(
        score=score,
        matched_keywords=matched_keywords,
        unrelated_concepts=unrelated_concepts,
        warnings=warnings,
    )


def build_caption_grounding_text(plan: CarouselPlan, discovery_angle: str = "") -> str:
    slide_headlines = " ".join(slide.headline for slide in plan.slides)
    fact_claims = " ".join(slide.fact_claim for slide in plan.slides if slide.fact_claim)
    return " ".join(
        part
        for part in (
            plan.topic,
            plan.niche,
            plan.title,
            plan.selected_pattern,
            plan.content_angle,
            slide_headlines,
            fact_claims,
            discovery_angle,
        )
        if part
    )


def extract_important_caption_keywords(plan: CarouselPlan) -> set[str]:
    source_text = " ".join(
        [
            plan.topic,
            plan.content_angle,
            " ".join(slide.headline for slide in plan.slides),
            " ".join(slide.fact_claim for slide in plan.slides if slide.fact_claim),
        ]
    )
    keywords: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", normalize_for_quality(source_text)):
        keyword = normalize_keyword(token)
        if len(keyword) < 4 or keyword in IMPORTANT_KEYWORD_STOPWORDS:
            continue
        keywords.add(keyword)
    return keywords


def normalize_keyword(value: str) -> str:
    keyword = value.lower().strip()
    if len(keyword) > 4 and keyword.endswith("ies"):
        return f"{keyword[:-3]}y"
    if len(keyword) > 4 and keyword.endswith("es"):
        keyword = keyword[:-2]
    elif len(keyword) > 4 and keyword.endswith("s"):
        keyword = keyword[:-1]
    return keyword


def find_unrelated_caption_concepts(
    plan: CarouselPlan,
    caption_text: str,
    grounding_text: str,
) -> list[str]:
    if is_neutron_star_topic(plan, grounding_text):
        return [
            concept
            for concept in NEUTRON_STAR_OFF_TOPIC_CONCEPTS
            if concept in caption_text and concept not in grounding_text
        ]
    return []


def is_neutron_star_topic(plan: CarouselPlan, grounding_text: str) -> bool:
    if any(marker in grounding_text for marker in SCIENCE_WEATHER_TOPIC_MARKERS):
        return False
    return any(marker in grounding_text for marker in NEUTRON_STAR_TOPIC_MARKERS)


def build_rule_based_caption(plan: CarouselPlan) -> str:
    topic = plan.topic.strip()
    niche = normalize_for_quality(plan.niche)
    first_headline = plan.slides[0].headline.strip().rstrip(".") if plan.slides else topic
    fact_claims = [
        slide.fact_claim.strip().rstrip(".")
        for slide in plan.slides
        if slide.fact_claim and not find_weak_phrase(slide.fact_claim)
    ]
    fact_one = fact_claims[0] if fact_claims else plan.content_angle.strip().rstrip(".")
    fact_two = fact_claims[1] if len(fact_claims) > 1 else ""
    extra_detail = f" {fact_two}." if fact_two else ""
    angle = plan.content_angle.strip().rstrip(".")
    safe_niche = plan.niche.strip().lower() or "this topic"

    if niche == "science":
        paragraphs = [
            f"Picture {topic} through one impossible-sounding image: {first_headline.lower()}.",
            f"The angle is simple: {angle}. That keeps the caption tied to the same idea as the slides.",
            f"Scientists think the key claim is careful but still extreme: {fact_one}.{extra_detail}",
            "Which detail makes this feel hardest to imagine?",
            "Save this post for careful science stories that keep wonder, context, and uncertainty together.",
        ]
    elif niche == "future":
        paragraphs = [
            f"Picture {topic} as a what-if scene built around {first_headline.lower()}.",
            f"In this scenario, the angle is {angle}. The slides stay short while the caption keeps the consequences clear.",
            f"The grounded details are {fact_one}.{extra_detail} That makes the idea feel possible without treating it as a promise.",
            "Which part of this future would you want to prepare for first?",
            "Save this post for future stories that keep speculation clear and grounded.",
        ]
    elif niche == "history":
        paragraphs = [
            f"Picture {topic} from one grounded moment: {first_headline.lower()}.",
            f"The angle is {angle}. That keeps the post focused on the lived details instead of drifting into a generic history lesson.",
            f"The caption context comes from the slide claims: {fact_one}.{extra_detail} The result is specific without pretending everyone lived the same story.",
            "Would you last one week there?",
            "Save this post for more strange history with the context kept in the caption.",
        ]
    else:
        paragraphs = [
            f"Picture {topic} through one vivid moment: {first_headline.lower()}.",
            f"The angle is {angle}. The slides stay short so the visuals can do their work.",
            f"The caption context comes from the slide claims: {fact_one}.{extra_detail} That keeps the post specific instead of drifting off-topic.",
            "Which detail would make you stop scrolling first?",
            f"Save this post for more {safe_niche} stories with the context kept in the caption.",
        ]

    return "\n\n".join(paragraphs)


def find_weak_phrase(value: str) -> str | None:
    lower = value.lower()
    for phrase in WEAK_PHRASES:
        if phrase in lower:
            return phrase
    return None


def is_missing_or_placeholder(value: str) -> bool:
    cleaned = normalize_for_quality(value)
    return cleaned in {"", "selected pattern", "exact selected pattern name", "pattern name", "none"}


def is_vague_content_angle(value: str) -> bool:
    cleaned = normalize_for_quality(value)
    if len(cleaned.split()) < 8:
        return True
    if cleaned in ABSTRACT_HEADLINE_LABELS:
        return True
    return any(
        phrase in cleaned
        for phrase in ("dark underbelly", "impressive facade", "hidden truth", "glamorous facade")
    )


def is_abstract_headline(value: str) -> bool:
    cleaned = normalize_for_quality(value)
    if cleaned in ABSTRACT_HEADLINE_LABELS:
        return True
    if find_weak_phrase(cleaned):
        return True
    words = cleaned.split()
    return len(words) <= 3 and any(
        word in cleaned
        for word in (
            "surface",
            "shadow",
            "hidden",
            "secrets",
            "hierarchy",
            "contrast",
            "truth",
            "glory",
            "reality",
            "life",
        )
    )


def normalize_for_quality(value: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", value.lower()).strip()
