"""Deterministic planner for hostless editorial explainer Reels."""

from __future__ import annotations

from app.content.explainer_schemas import ExplainerPlan, ExplainerScene


def plan_editorial_explainer_reel(topic: str, niche: str) -> ExplainerPlan:
    normalized = " ".join(topic.strip().split()) or "What is the relationship between oil prices and the dollar?"
    if "oil" in normalized.lower() and "dollar" in normalized.lower():
        return _oil_dollar_plan(normalized, niche)
    return _generic_plan(normalized, niche)


def plan_explainer_host_reel(topic: str, niche: str, host: object | None = None) -> ExplainerPlan:
    """Compatibility wrapper; the returned plan is hostless."""

    return plan_editorial_explainer_reel(topic, niche)


def _oil_dollar_plan(topic: str, niche: str) -> ExplainerPlan:
    return ExplainerPlan(
        topic=topic,
        niche=niche or "economy",
        explainer_angle="Explain the indirect oil price and dollar relationship without turning it into financial advice.",
        target_audience="Curious viewers who want a simple economy explanation in under 35 seconds.",
        hook="Oil and the dollar often move through the same global pressure system.",
        core_question="What is the relationship between oil prices and the dollar?",
        simple_answer=(
            "Oil is priced largely in dollars, so oil trade can affect dollar demand, importer costs, "
            "exporter revenue, inflation expectations, and currency pressure."
        ),
        key_terms=["oil price", "US dollar", "import bill", "export revenue", "inflation", "interest rates"],
        caveats=[
            "The relationship is indirect and context-dependent.",
            "Exchange rates also depend on inflation, interest rates, trade balances, and risk sentiment.",
            "This is educational content, not financial advice.",
        ],
        caption=(
            "Oil and the dollar are connected, but not in a simple one-way rule. Oil is traded globally "
            "largely in US dollars, which means importers need dollars to buy it and exporters often earn "
            "dollar revenue. When oil prices rise, import bills, inflation pressure, trade balances, and "
            "central-bank expectations can all shift. The effect on any currency depends on the full context, "
            "including interest rates and risk sentiment. This is an educational explainer, not financial advice."
        ),
        hashtags=["economy", "oilprices", "usdollar", "explained", "financeeducation"],
        scenes=[
            ExplainerScene(
                scene_number=1,
                duration_seconds=4.8,
                role="hook",
                visual_type="stock_video",
                visual_goal="Real-world establishing shot of oil logistics, fuel infrastructure, or tanker activity with a strong vertical focal point.",
                media_query="oil tanker fuel logistics energy infrastructure vertical",
                voiceover_line="Oil and the dollar are connected, but not by a simple magic switch.",
                on_screen_text="OIL VS DOLLAR",
                caption_priority_words=["oil", "dollar", "connected"],
                fact_claim="Oil and the dollar have an indirect relationship.",
                needs_fact_check=True,
                source_needed=True,
            ),
            ExplainerScene(
                scene_number=2,
                duration_seconds=5.3,
                role="setup",
                visual_type="stock_photo",
                visual_goal="Oil barrels, tanker, refinery, or energy market B-roll with clean vertical crop.",
                media_query="oil barrels refinery tanker energy market",
                voiceover_line="Because oil is priced globally largely in US dollars, buyers often need dollars first.",
                on_screen_text="PRICED IN USD",
                caption_priority_words=["priced", "dollars"],
                fact_claim="Oil is globally priced largely in US dollars.",
                needs_fact_check=True,
                source_needed=True,
            ),
            ExplainerScene(
                scene_number=3,
                duration_seconds=6.6,
                role="mechanism",
                visual_type="premium_infographic",
                visual_goal="Polished editorial cause-effect chain showing oil price rise, import bill rise, dollar demand, and currency pressure.",
                media_query="oil price import bill dollar demand currency pressure diagram",
                voiceover_line="If oil rises, import bills can rise too. That can add dollar demand and pressure local currencies.",
                on_screen_text="THE CHAIN",
                caption_priority_words=["import", "demand", "pressure"],
                fact_claim="Higher oil prices can raise import bills and affect currency pressure.",
                needs_fact_check=True,
                source_needed=True,
            ),
            ExplainerScene(
                scene_number=4,
                duration_seconds=5.7,
                role="example",
                visual_type="stock_photo",
                visual_goal="Importer or exporter context using shipping, fuel pricing, port logistics, or commodity flow imagery.",
                media_query="shipping port oil trade fuel import export vertical",
                voiceover_line="For exporters, higher oil can mean more dollar revenue, so the effect is different by country.",
                on_screen_text="EXPORTERS DIFFER",
                caption_priority_words=["exporters", "revenue"],
                fact_claim="Oil exporters may earn more dollar revenue when oil prices rise.",
                needs_fact_check=True,
                source_needed=True,
            ),
            ExplainerScene(
                scene_number=5,
                duration_seconds=5.1,
                role="takeaway",
                visual_type="premium_infographic",
                visual_goal="Premium editorial summary card over subtle energy-market texture: indirect relationship, context matters.",
                media_query="oil dollar indirect relationship context matters editorial infographic",
                voiceover_line="So the answer is: connected, but indirect. Inflation, rates, trade balance, and risk sentiment matter too.",
                on_screen_text="INDIRECT, NOT FIXED",
                caption_priority_words=["indirect", "rates", "risk"],
                fact_claim="The oil-dollar relationship is indirect and context-dependent.",
                needs_fact_check=True,
                source_needed=True,
            ),
        ],
    )


def _generic_plan(topic: str, niche: str) -> ExplainerPlan:
    return ExplainerPlan(
        topic=topic,
        niche=niche or "science",
        explainer_angle="Answer the question with one simple mechanism, one concrete example, and one caveat.",
        target_audience="Curious viewers who want a useful short explainer.",
        hook=f"{topic.rstrip('?')} has a simpler core than it first looks.",
        core_question=topic,
        simple_answer="Start with the mechanism, then check the context before making a broad claim.",
        key_terms=["mechanism", "example", "context"],
        caveats=["This is a simplified educational explanation."],
        caption=(
            "A good explainer starts with the mechanism, not the hype. This Reel breaks the question into "
            "a simple setup, a cause-effect step, a concrete example, and a caveat so the answer stays useful "
            "without pretending the real world is simpler than it is."
        ),
        hashtags=["explained", "learn", "education"],
        scenes=[
            ExplainerScene(
                scene_number=1,
                duration_seconds=4.5,
                role="hook",
                visual_type="stock_photo",
                visual_goal=f"Real-world establishing image that makes {topic} understandable in one second.",
                media_query=topic,
                voiceover_line=f"Here is the simple version of {topic.rstrip('?')}.",
                on_screen_text="SIMPLE VERSION",
            ),
            ExplainerScene(
                scene_number=2,
                duration_seconds=5.0,
                role="setup",
                visual_type="ai_image",
                visual_goal=f"Clear visual setup for {topic}, cinematic educational style.",
                media_query=topic,
                voiceover_line="First, separate the question from the noise around it.",
                on_screen_text="START HERE",
            ),
            ExplainerScene(
                scene_number=3,
                duration_seconds=6.0,
                role="mechanism",
                visual_type="premium_infographic",
                visual_goal=f"Polished editorial cause-effect infographic explaining {topic}.",
                media_query=topic,
                voiceover_line="Then follow the chain: one pressure creates another pressure.",
                on_screen_text="FOLLOW THE CHAIN",
            ),
            ExplainerScene(
                scene_number=4,
                duration_seconds=5.5,
                role="example",
                visual_type="stock_photo",
                visual_goal=f"Concrete real-world example visual for {topic}.",
                media_query=topic,
                voiceover_line="A real example makes the idea easier to remember.",
                on_screen_text="REAL EXAMPLE",
            ),
            ExplainerScene(
                scene_number=5,
                duration_seconds=5.0,
                role="takeaway",
                visual_type="premium_infographic",
                visual_goal=f"Premium editorial takeaway frame summarizing {topic}.",
                media_query=topic,
                voiceover_line="The useful answer is the one that keeps the caveat attached.",
                on_screen_text="KEEP THE CAVEAT",
            ),
        ],
    )
