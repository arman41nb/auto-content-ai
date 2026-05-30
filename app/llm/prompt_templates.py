"""Prompt templates for carousel planning."""

from __future__ import annotations


def build_carousel_prompt(
    topic: str,
    niche: str,
    slides: int,
    template: str,
    research_context: str = "",
    content_patterns: str = "",
    discovery_angle: str = "",
) -> str:
    research_block = research_context.strip() or "No research pack matched. Use only broadly safe claims."
    patterns_block = content_patterns.strip() or "No content patterns loaded. Use the default hook, setup, detail, contrast, CTA flow."
    discovery_block = discovery_angle.strip() or "No discovery angle provided."
    return f"""
Create an English-only Instagram carousel plan as strict JSON.
Positioning: Unreal Science & What-If Scenarios - science and future scenarios that feel unreal.
Primary growth goal: reach cold non-followers, earn watch time, DM shares, saves, and follows.

1. USER TOPIC
{topic}

2. NICHE
{niche}

3. SLIDE COUNT
{slides}

4. RESEARCH CONTEXT
Use this context when available. Prefer concrete visual details and safe claims from it.
Do not invent unsupported specific facts.

{research_block}

5. CONTENT PATTERNS
Choose one pattern from this list and follow its slide_structure.
Use its name exactly in selected_pattern.

{patterns_block}

6. DISCOVERY ANGLE
Use this as extra grounding when available.

{discovery_block}

7. OUTPUT JSON SCHEMA RULES
Visual template: {template}

Rules:
- Output only valid JSON. No markdown, no code fences, no explanation.
- Use exactly {slides} slides.
- Add selected_pattern: the exact name of the one chosen content pattern.
- Add content_angle: one sentence that states the single narrative angle of the post.
- Every slide must follow content_angle. Do not make a list of unrelated school facts.
- Make slide 1 a true cold-audience cover: understandable in under 1 second, emotionally charged, visual, and driven by a strong curiosity gap.
- Do not start with a slow educational intro. Start with survival, shock, impossible scale, or an immediate visible consequence.
- Avoid cover wording like "What was life like..." or generic educational questions.
- Follow the selected pattern's slide_structure, while keeping the narrative flow of hook, setup, specific reality, twist/contrast, CTA.
- For more than 5 slides, deepen the same chain of tension instead of changing topics.
- Headlines must be 8 words or fewer.
- Subtext must be 14 words or fewer.
- Write like a high-performing Instagram history/science/future carousel: sharp, specific, DM-shareable, save-worthy, and follow-worthy.
- Avoid these generic or abstract phrases anywhere in the JSON, including captions: "Explore...", "Discover...", "Share your thoughts", "A day in the life...", "From dawn till dusk", "secrets of a bygone era", "Beneath the Surface", "Hidden Lives", "Social Hierarchy", "City of Contrasts", "Roman Shadows", "A hidden truth", "hidden truth", "dirty secret".
- Avoid abstract slide headlines. Prefer concrete daily realities, strange details, vivid contrasts, and clear CTAs.
- Bad abstract headlines: "Rome's Glory", "Crowded Reality", "Simple Life", "Sharp Contrasts", "Survive Rome".
- Better concrete headlines: "Smoke Hits Before Marble", "Your Apartment Was Cramped", "Dinner Was Mostly Bread", "Baths Were Social Hubs", "Would You Last A Week?"
- Prefer tension, consequence, contrast, survival, impossible scale, sensory detail, or surprise over generic educational wording.
- Make the final slide CTA specific and natural, e.g. "Would you survive one week there?", "Save this for more strange history.", or "Comment 'ROME' for part 2."
- Keep slide text short and visual. Use the caption to add the context and story that would overload the images.
- Keep each slide skimmable enough for an 8-12 second Reel version.
- For what-if disaster topics, show the immediate consequence first, then the simple chain reaction.
- For what-if disaster topics, use a Reel-first consequence chain instead of school-like labels:
  Slide 1/Cover: direct impossible hook, e.g. "The Ocean Moves First" with subtext like "No warning. No roads."
  Slide 2: immediate consequence, e.g. "Streets Become Rivers".
  Slide 3: human consequence, e.g. "Power Fails Fast".
  Slide 4: hidden consequence, e.g. "Clean Water Disappears".
  Slide 5: survival question CTA, e.g. "Where Would You Go?"
- For what-if disaster topics, avoid "New ecosystems" unless the topic truly supports it visually and scientifically.
- For what-if disaster topics, avoid generic CTA wording like "prepare for the unexpected", "follow for more", or "share your thoughts".
- For what-if disaster topics, avoid broad unsupported claims like "millions displaced" unless the research context grounds them.
- For what-if disaster topics, write slide text like short voiceover beats: concrete, sequential, and survival-oriented.
- For extreme science topics, make the impossible-feeling visual clear before the explanation.
- For future scenarios, frame speculation clearly and make the human consequence visible.
- Do not confuse short slide text with a short caption. The caption must be longer than the slide text because it carries the context.
- The caption must be Instagram-native storytelling, 80 to 140 words.
- Ground the caption in the current plan only: topic, niche, title, selected_pattern, content_angle, slide headlines, fact_claims, and discovery angle when available.
- The caption must include at least 2 important keywords from the topic, content_angle, slide headlines, or fact_claims.
- Do not import stale concepts from other science topics. If the plan is about neutron stars, dense matter, collapsed stars, supernova cores, spoonfuls/teaspoons/sugar cubes, billions of tons, gravity, or city-sized stars, do not mention exoplanet weather, glass rain, alien atmosphere, or worlds beyond Earth with weather unless those concepts appear in this plan.
- Caption structure: 5 short paragraphs separated by line breaks.
- Caption paragraph 1: a strong visual or story hook that makes sense to someone who has never seen the page.
- Caption paragraphs 2-3: simple explanation, context, or grounded detail.
- Caption paragraph 4: one natural question CTA.
- Caption paragraph 5: one natural save or follow CTA.
- Do not put hashtags in the caption. Hashtags belong only in the hashtags array.
- Do not use vague or generic caption phrases like "Save for more", "Explore...", "Discover...", "Learn more...", or "Uncover more...".
- Science captions must use careful uncertainty language when needed: may, could, scientists think, researchers suggest, or one possible explanation. Never present speculative science as guaranteed fact.
- Future captions must clearly frame speculation with language like what if, could, might, or in this scenario.
- History captions must be vivid but grounded. Do not add unsupported precise claims, dates, numbers, or dramatic certainty beyond the research context.
- Use a consistent cinematic documentary style across all image prompts.
- Each image_prompt must visually match the exact headline/subtext, not just the broad topic.
- Each image_prompt must include vertical composition, a text-safe area instruction, and the exact phrase "no text".
- For what-if disaster image prompts, vary camera shots by slide: wide establishing shot, street-level survival perspective, interior/human-scale consequence, infrastructure/hidden consequence, then close-up survival detail.
- For what-if disaster image prompts, include "natural cinematic lighting, realistic documentary still, no typography, no signage, no text" and avoid repeating a generic flooded city five times.
- For what-if disaster slide 5, do not request a drowning face or horror poster expression; prefer a survivor seen from behind looking at a flooded skyline, or a hand holding an emergency radio above floodwater.
- For history/science content, avoid unsupported extreme claims and phrase uncertainty carefully.
- Never ask the image model to place words, letters, labels, logos, captions, or typography inside the image.
- Use text_position only as one of: bottom_left, center, top_left.
- Use composition_hint to reserve readable negative space for overlay text.
- Use role only as one of: hook, setup, fact, twist, CTA, final.
- Hashtags must be an array without # symbols.
- All content must be in English.

Return JSON with this exact shape:
{{
  "topic": "{topic}",
  "niche": "{niche}",
  "title": "Short carousel title",
  "selected_pattern": "Exact selected pattern name",
  "content_angle": "One-sentence narrative angle that every slide follows.",
  "target_audience": "Who this is for",
  "tone": "cinematic, clear, documentary-style",
  "caption": "80-140 word Instagram-native story caption with short paragraphs, one question CTA, and one save/follow CTA.",
  "hashtags": ["history", "ancientrome"],
  "slides": [
    {{
      "slide_number": 1,
      "role": "hook",
      "tag": "SHORT TAG",
      "headline": "Short sharp headline",
      "subtext": "Optional specific tension line.",
      "visual_goal": "What this exact slide moment should communicate.",
      "image_prompt": "cinematic realistic vertical composition of the exact slide moment, text-safe dark negative space in the lower third, no text",
      "text_position": "bottom_left",
      "composition_hint": "leave dark negative space in the lower third for text",
      "fact_claim": "A careful factual claim represented on this slide.",
      "needs_fact_check": true
    }}
  ]
}}
""".strip()


def build_repair_prompt(original_prompt: str, raw_response: str, error: str) -> str:
    return f"""
The previous response was invalid for this task.

Validation/parsing error:
{error}

Invalid response:
{raw_response}

Rewrite it as valid JSON only, following the original instructions exactly.
Pay special attention to caption validation: the caption must be 80-140 words, use 5 short paragraphs with line breaks, include one question CTA, include one save/follow CTA, and contain no hashtags.

Original instructions:
{original_prompt}
""".strip()


def build_quality_retry_prompt(original_prompt: str, valid_response: str, issues: list[str]) -> str:
    issue_text = "\n".join(f"- {issue}" for issue in issues)
    return f"""
The previous response was valid JSON, but the writing was too generic or weak for Instagram.

Quality issues:
{issue_text}

Valid but weak response:
{valid_response}

Regenerate the full carousel plan as valid JSON only.
Keep the same topic, niche, slide count, JSON shape, and English-only requirement.
Make the content_angle tighter, make slide 1 understandable in under 1 second for cold non-followers, make the narrative more connected, and replace weak phrasing with specific tension.
Prioritize survival, shock, impossible scale, immediate visible consequence, DM-share potential, saves, and follows.
Do not use weak phrases anywhere in the JSON, including captions.
Do not use abstract labels like "Rome's Glory", "Crowded Reality", "Simple Life", "Sharp Contrasts", "Beneath the Surface", "Hidden Lives", "City of Contrasts", "hidden truth", or "dirty secret".
Use concrete, visual headlines tied to a specific scene, object, sensory detail, impossible scale, or consequence.
Rewrite the caption as 80-140 words of Instagram-native storytelling.
Use exactly 5 short paragraphs separated by line breaks: visual/story hook, context, added detail, one question CTA, one save/follow CTA.
Keep hashtags out of the caption. Do not use "Save for more", "Explore", "Discover", "Learn more", "Uncover more", clickbait, or overpromises.
For science, use careful uncertainty language. For future topics, clearly frame speculation. For history, stay vivid but grounded.

Original instructions:
{original_prompt}
""".strip()


def build_caption_retry_prompt(valid_response: str, issues: list[str], discovery_angle: str = "") -> str:
    issue_text = "\n".join(f"- {issue}" for issue in issues)
    discovery_block = discovery_angle.strip() or "No discovery angle provided."
    return f"""
The carousel plan is valid, but the caption still does not meet the Instagram-native storytelling rules.

Caption issues:
{issue_text}

Existing valid carousel plan:
{valid_response}

Discovery angle:
{discovery_block}

Rewrite only the caption.

Caption rules:
- English only.
- 80-140 words.
- Ground the caption in the current plan only: topic, niche, title, selected_pattern, content_angle, slide headlines, fact_claims, and discovery angle when available.
- Include at least 2 important keywords from the topic, content_angle, slide headlines, or fact_claims.
- Do not import stale concepts from other topics. If the plan is about neutron stars or dense stellar matter, do not mention exoplanet weather, glass rain, alien atmosphere, or worlds beyond Earth with weather unless those terms appear in the plan above.
- Exactly 5 short paragraphs separated by line breaks.
- Paragraph 1: strong visual or story hook.
- Paragraphs 2-3: simple context, explanation, or grounded detail.
- Paragraph 4: one natural question CTA.
- Paragraph 5: one natural save or follow CTA.
- No hashtags.
- Do not use "Save for more", "Explore", "Discover", "Learn more", "Uncover more", clickbait, or overpromises.
- For science, use careful uncertainty language such as may, could, scientists think, researchers suggest, or one possible explanation.
- For future topics, clearly frame speculation with what if, could, might, or in this scenario.
- For history, stay vivid but grounded and avoid unsupported precise claims.

Return only this JSON shape:
{{
  "caption": "The rewritten caption with line breaks"
}}
""".strip()
