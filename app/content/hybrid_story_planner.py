"""Deterministic planner for hybrid story explainer Reels."""

from __future__ import annotations

from app.content.hybrid_story_schemas import HybridStoryPlan, HybridStoryScene
from app.mascot.mascot_profile import MascotProfile


def plan_hybrid_story_reel(topic: str, niche: str, mascot: MascotProfile) -> HybridStoryPlan:
    normalized = " ".join(topic.strip().split()) or "What is the relationship between oil prices and the dollar?"
    if "oil" in normalized.lower() and "dollar" in normalized.lower():
        return _oil_dollar_plan(normalized, niche or "economy", mascot)
    return _generic_plan(normalized, niche or "science", mascot)


def _oil_dollar_plan(topic: str, niche: str, mascot: MascotProfile) -> HybridStoryPlan:
    return HybridStoryPlan(
        topic=topic,
        niche=niche,
        title="Oil, Dollars, and the Bill",
        story_angle=(
            "A small importer sees an oil invoice rise, Miko guides the mechanism from the side, "
            "and real energy trade scenes carry the explanation."
        ),
        audience="Curious viewers who want a concrete economy explanation without trading advice.",
        core_question=topic,
        simple_answer=(
            "Oil is often priced in US dollars, so higher oil prices can raise dollar needs for importers, "
            "but exporters and broader macro conditions can change the effect."
        ),
        caveat=(
            "The relationship is indirect and context-dependent. Importers, exporters, rates, inflation, "
            "trade balances, and risk sentiment can all change the outcome. This is not financial advice."
        ),
        caption=(
            "Oil and the dollar are connected through trade, invoices, and currency demand, not through a simple one-way rule. "
            "If an importer buys oil priced in US dollars, a higher oil price can mean a bigger dollar bill. That can raise demand "
            "for dollars and pressure the local currency. Exporters can feel the same price move differently because they may receive "
            "more dollar revenue. The link is indirect, context-dependent, and not financial advice."
        ),
        hashtags=["economy", "oilprices", "usdollar", "explained", "learnfinance"],
        mascot_id=mascot.mascot_id,
        caption_style="hybrid_editorial",
        scenes=[
            HybridStoryScene(
                scene_number=1,
                role="hook",
                duration_target=3.6,
                narrative_function="Open on a real energy cost moment, not the mascot.",
                voiceover_line="When oil rises, the dollar can matter more.",
                visual_type="real_world_broll",
                media_query="vertical fuel tanker gas station oil price economy",
                ai_scene_prompt=(
                    "realistic vertical editorial scene of a fuel tanker at a busy gas station, oil price pressure implied "
                    "through pumps, trucks, and receipts, no text, no logos, no host"
                ),
                mascot_presence="none",
                mascot_frame_share_target=0.0,
                required_context_objects=["fuel tanker", "gas station", "receipt or pump", "oil context"],
                forbidden_visuals=["giant mascot", "human presenter close-up", "price chart only", "text"],
                caption_text="Oil bill rises",
                key_words=["oil", "dollar", "bill"],
                fact_claim="Oil prices can affect import bills and currency demand.",
                source_needed=True,
                visual_objective="Ground the viewer in a real oil-cost scene within the first second.",
                composition_notes="Subject-first real-world vertical crop with caption-safe lower third and no title card treatment.",
                transition_intent="hard cut from real cost to the person facing the bill",
            ),
            HybridStoryScene(
                scene_number=2,
                role="question",
                duration_target=3.8,
                narrative_function="Put the question inside a proxy business problem.",
                voiceover_line="An importer sees a fuel invoice: why dollars?",
                questioner_line_optional="Why is this in dollars?",
                proxy_role_optional="importer",
                visual_type="mascot_context_scene",
                media_query="small importer office fuel invoice dollar payment",
                ai_scene_prompt=(
                    "realistic importer office desk with fuel invoice, calculator, shipping papers, small Miko mascot as a tiny desk-side guide, "
                    "Miko occupies about 18 percent of frame, pointing at invoice, no readable text, no logos"
                ),
                mascot_presence="side_guide",
                mascot_frame_share_target=0.18,
                required_context_objects=["importer desk", "fuel invoice", "calculator", "shipping papers", "small Miko"],
                forbidden_visuals=["close-up human presenter", "giant centered mascot", "blank background", "readable invoice text"],
                caption_text="Why dollars?",
                key_words=["importer", "invoice", "dollars"],
                fact_claim="Many oil transactions are priced or settled in US dollars.",
                source_needed=True,
                visual_objective="Make the abstract relationship a concrete invoice question.",
                composition_notes="Importer/proxy is implied by hands or side view; Miko is small and useful, not the main subject.",
                transition_intent="cut on the question into the setup",
            ),
            HybridStoryScene(
                scene_number=3,
                role="setup",
                duration_target=3.9,
                narrative_function="Explain the concrete setup before the mechanism.",
                voiceover_line="Many oil contracts use dollars, so importers need dollars.",
                visual_type="ai_realistic_scene",
                media_query="oil invoice port office dollar payment shipping documents",
                ai_scene_prompt=(
                    "realistic editorial vertical scene of shipping documents, oil invoice, port window background, wallet and dollar payment cue, "
                    "no mascot, no readable text, no logos, premium documentary lighting"
                ),
                mascot_presence="none",
                mascot_frame_share_target=0.0,
                required_context_objects=["oil invoice", "shipping documents", "wallet", "port background"],
                forbidden_visuals=["mascot portrait", "abstract dollar wallpaper", "PowerPoint slide", "readable text"],
                caption_text="The invoice sets it up",
                key_words=["invoice", "contract", "dollars"],
                fact_claim="Oil pricing in dollars can make dollar funding relevant for importers.",
                source_needed=True,
                visual_objective="Show the invoice mechanics through objects instead of a title card.",
                composition_notes="Tabletop/editorial object scene with layered depth and usable negative space for captions.",
                transition_intent="push into mechanism",
            ),
            HybridStoryScene(
                scene_number=4,
                role="mechanism",
                duration_target=4.4,
                narrative_function="Reveal the cause-effect chain with restrained motion graphics.",
                voiceover_line="Pricier barrels mean more dollars for the same shipment.",
                mascot_line_optional="Follow the bill.",
                visual_type="premium_infographic",
                media_query="oil price import bill dollar demand currency pressure infographic",
                ai_scene_prompt=(
                    "premium editorial cause-effect infographic over subtle energy trade backdrop: oil price up, import bill up, dollar demand up, currency pressure up, "
                    "small Miko guide in corner only if useful, no crowded text"
                ),
                mascot_presence="small_corner",
                mascot_frame_share_target=0.12,
                required_context_objects=["oil price cue", "import bill", "dollar demand meter", "currency pressure"],
                forbidden_visuals=["PowerPoint chart", "giant labels", "full-screen dry chart", "giant mascot"],
                caption_text="The chain",
                key_words=["bill", "demand", "pressure"],
                fact_claim="Higher oil prices can raise dollar demand and currency pressure for importers.",
                source_needed=True,
                visual_objective="Make the mechanism memorable without overfilling the frame.",
                composition_notes="Cards reveal sequentially with strong spacing; Miko remains a tiny guide or is omitted.",
                transition_intent="match arrow reveal into consequence scene",
            ),
            HybridStoryScene(
                scene_number=5,
                role="consequence",
                duration_target=3.8,
                narrative_function="Show the real-world pressure after the mechanism.",
                voiceover_line="That can pressure the local currency.",
                visual_type="hybrid_broll_overlay",
                media_query="currency exchange fuel station logistics importer economy",
                ai_scene_prompt=(
                    "real-world fuel station or logistics scene with subtle editorial overlay space for dollar demand and local currency pressure, "
                    "no human host, no readable signs, no logos"
                ),
                mascot_presence="none",
                mascot_frame_share_target=0.0,
                required_context_objects=["fuel or logistics scene", "currency cue", "real-world cost context"],
                forbidden_visuals=["mascot filler", "abstract chart only", "stock image with no oil context"],
                caption_text="Currency pressure",
                key_words=["demand", "currency", "pressure"],
                fact_claim="More dollar demand can pressure local currency for oil importers.",
                source_needed=True,
                visual_objective="Connect the mechanism back to a real cost environment.",
                composition_notes="Use real-world b-roll with restrained overlay, not a standalone title.",
                transition_intent="cut to exporter contrast",
            ),
            HybridStoryScene(
                scene_number=6,
                role="contrast",
                duration_target=3.8,
                narrative_function="Show that exporters can feel the same oil move differently.",
                voiceover_line="Exporters can earn more dollars, so the shock differs.",
                visual_type="real_world_broll",
                media_query="oil tanker export terminal crude oil shipping vertical",
                ai_scene_prompt=(
                    "realistic vertical oil tanker export terminal scene, port cranes and tanker, exporter side of oil trade, "
                    "premium documentary color, no text, no logos, no presenter"
                ),
                mascot_presence="none",
                mascot_frame_share_target=0.0,
                required_context_objects=["oil tanker", "export terminal", "port or shipping route"],
                forbidden_visuals=["human host close-up", "trading recommendation", "generic city skyline"],
                caption_text="Exporters differ",
                key_words=["exporter", "dollars", "different"],
                fact_claim="Oil exporters may receive more dollar revenue when oil prices rise.",
                source_needed=True,
                caveat_required=True,
                visual_objective="Give the audience a contrast so the explanation is not one-way.",
                composition_notes="Real-world exporter scene with clear tanker/export context.",
                transition_intent="cut from tanker to nuance board",
            ),
            HybridStoryScene(
                scene_number=7,
                role="nuance",
                duration_target=4.0,
                narrative_function="Add the macro caveat that prevents oversimplification.",
                voiceover_line="Rates, inflation, trade balances, and fear can change it.",
                mascot_line_optional="Context changes the answer.",
                visual_type="mascot_small_overlay",
                media_query="macro economy dashboard interest rates inflation trade balance risk sentiment",
                ai_scene_prompt=(
                    "realistic macro economy desk scene with charts as abstract shapes, newspaper, exchange board blur, and small Miko side guide pointing to four context objects, "
                    "Miko occupies about 16 percent of frame, no readable text, no logos"
                ),
                mascot_presence="side_guide",
                mascot_frame_share_target=0.16,
                required_context_objects=["rates cue", "inflation cue", "trade balance cue", "risk sentiment cue", "small Miko"],
                forbidden_visuals=["giant mascot", "floating icon-only slide", "readable chart text", "financial advice"],
                caption_text="Context changes it",
                key_words=["rates", "inflation", "context"],
                fact_claim="Currency effects depend on broader macroeconomic context.",
                source_needed=True,
                caveat_required=True,
                visual_objective="Make nuance visual through context objects, not generic icons.",
                composition_notes="Miko acts as a side guide near objects; the desk/context remains dominant.",
                transition_intent="soft cut into final practical takeaway",
            ),
            HybridStoryScene(
                scene_number=8,
                role="takeaway",
                duration_target=3.9,
                narrative_function="Give a saveable final sentence that keeps the caveat attached.",
                voiceover_line="Real, but indirect: one pressure, not the whole story.",
                mascot_line_optional="One pressure, not the whole story.",
                visual_type="takeaway_scene",
                media_query="oil barrel dollar flow map invoice takeaway indirect relationship",
                ai_scene_prompt=(
                    "premium realistic tabletop scene with small oil barrel, dollar flow line, map, invoice, and small Miko as a side guide occupying about 20 percent of frame, "
                    "clear final composition, no readable text, no logos, no giant mascot"
                ),
                mascot_presence="side_guide",
                mascot_frame_share_target=0.20,
                required_context_objects=["oil barrel", "dollar flow", "map", "invoice", "small Miko"],
                forbidden_visuals=["giant centered mascot", "blank background", "title-only slide", "trading advice"],
                caption_text="Real, but indirect",
                key_words=["real", "indirect", "context"],
                fact_claim="The oil-dollar relationship is indirect and context-dependent.",
                source_needed=True,
                caveat_required=True,
                visual_objective="Close with a memorable object scene that sums up the explanation.",
                composition_notes="Small Miko points at the relationship; the oil/dollar objects carry the meaning.",
                transition_intent="final hold",
            ),
        ],
    )


def _generic_plan(topic: str, niche: str, mascot: MascotProfile) -> HybridStoryPlan:
    return HybridStoryPlan(
        topic=topic,
        niche=niche,
        title=topic.rstrip("?"),
        story_angle="A concrete situation explains the abstract question with Miko as a small guide.",
        audience="Curious viewers who want a useful short explanation.",
        core_question=topic,
        simple_answer="Start with a real moment, follow the mechanism, contrast a second case, then keep the caveat attached.",
        caveat="This is a simplified educational explanation. Context matters and this is not financial advice if money decisions are involved.",
        caption=(
            "A hybrid story explainer works by turning an abstract question into a concrete situation, then showing the mechanism, the consequence, "
            "the contrast, the caveat, and the takeaway. Miko is used as a small guide, not as the whole frame. Context matters."
        ),
        hashtags=["explained", "learn", "education"],
        mascot_id=mascot.mascot_id,
        caption_style="hybrid_editorial",
        scenes=[
            HybridStoryScene(
                scene_number=index,
                role=role,
                duration_target=3.6 if index != 4 else 4.2,
                narrative_function=function,
                voiceover_line=line,
                questioner_line_optional="What is happening here?" if role == "question" else "",
                proxy_role_optional="curious_friend" if role == "question" else "none",
                visual_type=visual_type,
                media_query=topic,
                ai_scene_prompt=f"premium vertical realistic scene for {topic}, concrete objects, small Miko only if specified, no text, no logos",
                mascot_presence=mascot_presence,
                mascot_frame_share_target=share,
                required_context_objects=["concrete object", "realistic setting", "clear subject"],
                forbidden_visuals=["title card", "giant mascot", "blank background", "human host close-up"],
                caption_text=caption,
                key_words=caption.lower().split()[:3],
                fact_claim=line,
                source_needed=False,
                visual_objective=function,
                composition_notes="Meaningful scene with concrete context and caption-safe space.",
                transition_intent="cut on phrase boundary",
            )
            for index, (role, visual_type, mascot_presence, share, function, line, caption) in enumerate(
                [
                    ("hook", "real_world_broll", "none", 0.0, "Start in the real world.", f"Start with one concrete moment behind {topic.rstrip('?')}.", "Start concrete"),
                    ("question", "mascot_context_scene", "side_guide", 0.18, "Let a proxy ask the question.", "A curious person asks what is really driving the change.", "The question feels real"),
                    ("setup", "ai_realistic_scene", "none", 0.0, "Build the example.", "The setup matters before the mechanism can make sense.", "Set up the example"),
                    ("mechanism", "premium_infographic", "small_corner", 0.12, "Reveal cause and effect.", "Then follow the chain from cause to response.", "Follow the chain"),
                    ("consequence", "hybrid_broll_overlay", "none", 0.0, "Show the consequence.", "A real-world consequence makes the idea easier to remember.", "Real consequence"),
                    ("contrast", "real_world_broll", "none", 0.0, "Show a second case.", "A different case can feel the same force differently.", "Different case"),
                    ("nuance", "mascot_small_overlay", "side_guide", 0.16, "Attach the caveat.", "The useful answer keeps the context attached.", "Context changes it"),
                    ("takeaway", "takeaway_scene", "side_guide", 0.2, "End with the saveable idea.", "The takeaway is simple, but not oversimplified.", "Simple, not simplistic"),
                ],
                start=1,
            )
        ],
    )
