from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.content.planner import (  # noqa: E402
    build_caption_alignment_report,
    build_rule_based_caption,
    find_caption_quality_issues,
)
from app.content.schemas import CarouselPlan  # noqa: E402


def make_plan(
    caption: str,
    topic: str = "A star so dense a spoonful weighs billions of tons",
    content_angle: str = (
        "This post explains neutron star density through a spoonful analogy, gravity, "
        "and the collapsed stellar core left after a supernova."
    ),
) -> CarouselPlan:
    return CarouselPlan.model_validate(
        {
            "topic": topic,
            "niche": "science",
            "title": "Billion-Ton Spoon",
            "selected_pattern": "Strange Detail",
            "content_angle": content_angle,
            "target_audience": "Curious space fans",
            "tone": "cinematic, clear, documentary-style",
            "caption": caption,
            "hashtags": ["space", "science"],
            "slides": [
                {
                    "slide_number": 1,
                    "role": "hook",
                    "tag": "SPOON",
                    "headline": "A Spoonful Weighs Billions",
                    "subtext": "Human scale breaks here.",
                    "visual_goal": "Show a spoon beside a neutron star.",
                    "image_prompt": "cinematic realistic vertical composition of a spoon beside a neutron star, text-safe negative space, no text",
                    "text_position": "bottom_left",
                    "composition_hint": "leave dark negative space in the lower third for text",
                    "fact_claim": "A spoonful of neutron star matter could weigh billions of tons.",
                    "needs_fact_check": True,
                },
                {
                    "slide_number": 2,
                    "role": "setup",
                    "tag": "CORE",
                    "headline": "A Collapsed Stellar Core",
                    "subtext": "A dead giant leaves this behind.",
                    "visual_goal": "Show a compact collapsed stellar core.",
                    "image_prompt": "cinematic realistic vertical composition of a compact collapsed stellar core, text-safe negative space, no text",
                    "text_position": "bottom_left",
                    "composition_hint": "leave dark negative space in the lower third for text",
                    "fact_claim": "Neutron stars can form from collapsed cores after supernova explosions.",
                    "needs_fact_check": True,
                },
                {
                    "slide_number": 3,
                    "role": "fact",
                    "tag": "DENSE",
                    "headline": "Dense Matter Crushes Inward",
                    "subtext": "Gravity compresses almost everything.",
                    "visual_goal": "Show dense matter under extreme gravity.",
                    "image_prompt": "cinematic realistic vertical composition of dense matter under extreme gravity, text-safe negative space, no text",
                    "text_position": "bottom_left",
                    "composition_hint": "leave dark negative space in the lower third for text",
                    "fact_claim": "Neutron star gravity compresses matter to extreme density.",
                    "needs_fact_check": True,
                },
                {
                    "slide_number": 4,
                    "role": "twist",
                    "tag": "CITY",
                    "headline": "City-Sized Star Physics",
                    "subtext": "Small does not mean gentle.",
                    "visual_goal": "Show a city-sized star bending light.",
                    "image_prompt": "cinematic realistic vertical composition of a city-sized star bending light, text-safe negative space, no text",
                    "text_position": "bottom_left",
                    "composition_hint": "leave dark negative space in the lower third for text",
                    "fact_claim": "A neutron star can pack stellar mass into a city-sized object.",
                    "needs_fact_check": True,
                },
                {
                    "slide_number": 5,
                    "role": "CTA",
                    "tag": "SAVE",
                    "headline": "Would You Approach It",
                    "subtext": "Save the impossible scale.",
                    "visual_goal": "Show a distant spacecraft near a neutron star.",
                    "image_prompt": "cinematic realistic vertical composition of a distant spacecraft near a neutron star, text-safe negative space, no text",
                    "text_position": "bottom_left",
                    "composition_hint": "leave dark negative space in the lower third for text",
                    "fact_claim": "Neutron stars reveal extreme physics in compact objects.",
                    "needs_fact_check": True,
                },
            ],
        }
    )


class CaptionAlignmentTests(unittest.TestCase):
    def test_neutron_star_rejects_glass_rain_or_exoplanet_weather_caption(self) -> None:
        plan = make_plan(
            "A spoonful of neutron star matter could weigh billions of tons, but the caption suddenly drifts into another sky.\n\n"
            "Scientists think exoplanet weather could involve glass rain, alien atmosphere layers, and winds on distant planet scenes far from this collapsed star.\n\n"
            "That stale idea may sound cinematic, but it does not explain dense matter, gravity, a supernova core, or the city-sized star in these slides.\n\n"
            "Which neutron star detail should stay in focus?\n\n"
            "Save this post for careful science stories that stay tied to the current topic."
        )

        issues = find_caption_quality_issues(plan)
        report = build_caption_alignment_report(plan)

        self.assertTrue(any("unrelated concepts" in issue for issue in issues))
        self.assertIn("glass rain", report.unrelated_concepts)
        self.assertIn("exoplanet weather", report.unrelated_concepts)

    def test_glass_rain_topic_may_mention_exoplanet_weather(self) -> None:
        plan = make_plan(
            topic="A planet where it may rain glass",
            content_angle=(
                "This post explains how an exoplanet atmosphere, extreme wind, and heat "
                "could make alien weather feel violent."
            ),
            caption=(
                "Imagine an exoplanet where the storm itself feels sharp.\n\n"
                "Scientists think an alien atmosphere with extreme heat and fierce wind could create weather unlike anything on Earth.\n\n"
                "In that context, glass rain is not a fantasy flourish; it is the strange visual hook that keeps the planet, atmosphere, and weather connected.\n\n"
                "Which part of that alien weather would you want explained first?\n\n"
                "Save this post for careful science stories that keep wonder and uncertainty together."
            ),
        )

        issues = find_caption_quality_issues(plan)

        self.assertFalse(any("unrelated concepts" in issue for issue in issues))

    def test_caption_under_40_words_is_still_rejected(self) -> None:
        valid = make_plan(
            "A neutron star turns the spoon into a scale problem.\n\n"
            "Scientists think dense matter and gravity could compress a stellar core beyond ordinary intuition.\n\n"
            "A spoonful may weigh billions of tons because a collapsed star is not normal matter.\n\n"
            "Which detail feels strangest?\n\n"
            "Save this post for careful science stories."
        ).model_dump()
        valid["caption"] = "Neutron stars are dense.\n\nWould you approach one?\n\nSave this post."

        with self.assertRaises(ValidationError):
            CarouselPlan.model_validate(valid)

    def test_caption_generic_phrases_are_still_rejected(self) -> None:
        plan = make_plan(
            "Discover a neutron star through a spoonful that could weigh billions of tons.\n\n"
            "Scientists think dense matter and gravity could compress a collapsed stellar core after a supernova into something wildly compact.\n\n"
            "The slides keep returning to the same idea: a city-sized star can make normal scale feel useless.\n\n"
            "Which part should we explore next?\n\n"
            "Save this post for careful science stories that keep the context in view."
        )

        issues = find_caption_quality_issues(plan)

        self.assertTrue(any("weak phrase" in issue for issue in issues))

    def test_rule_based_science_fallback_uses_current_plan_not_weather_template(self) -> None:
        plan = make_plan(
            "A neutron star turns a spoon into a scale problem.\n\n"
            "Scientists think dense matter and gravity could compress a stellar core beyond ordinary intuition.\n\n"
            "A spoonful may weigh billions of tons because a collapsed star is not normal matter.\n\n"
            "Which detail feels strangest?\n\n"
            "Save this post for careful science stories."
        )

        caption = build_rule_based_caption(plan).lower()

        self.assertIn("neutron star", caption)
        self.assertIn("spoonful", caption)
        self.assertNotIn("glass rain", caption)
        self.assertNotIn("exoplanet weather", caption)


if __name__ == "__main__":
    unittest.main()
