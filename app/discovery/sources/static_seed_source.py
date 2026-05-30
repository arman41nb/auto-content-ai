"""Local fallback discovery topics."""

from __future__ import annotations

from app.discovery.schemas import DiscoveryLane, TopicCandidate
from app.discovery.sources.base import DiscoverySource


def _seed(topic: str, angle: str, keywords: list[str], lane: str | None = None) -> dict[str, object]:
    return {
        "topic": topic,
        "angle": angle,
        "keywords": keywords,
        "lane": lane,
    }


LANE_SEED_TOPICS: dict[str, list[dict[str, object]]] = {
    "what_if_disaster": [
        _seed("What if oxygen disappeared for 5 seconds?", "Show the instant body, fire, sky, and pressure consequences.", ["what if", "oxygen", "body", "earth", "survival"]),
        _seed("What if Earth stopped rotating for 5 seconds?", "A fast momentum disaster with oceans and atmosphere moving first.", ["what if", "earth", "rotation", "ocean", "disaster"]),
        _seed("What if the Moon disappeared?", "Tides, nights, and Earth's wobble become one visible chain reaction.", ["what if", "moon", "earth", "ocean", "gravity"]),
        _seed("What if gravity doubled for one day?", "Make weight, buildings, bodies, and oceans feel instantly heavier.", ["what if", "gravity", "body", "survival", "earth"]),
        _seed("What if the Sun vanished for 8 minutes?", "The first seconds are normal, then the sky and gravity story turns strange.", ["what if", "sun", "earth", "darkness", "gravity"]),
        _seed("What if oceans rose overnight?", "A simple flooded-city visual with immediate survival stakes.", ["what if", "ocean", "earth", "flood", "survival"]),
        _seed("What if Earth lost its magnetic field?", "Turn invisible shielding into auroras, radiation, and damaged satellites.", ["what if", "earth", "magnetic field", "sun", "radiation"]),
        _seed("What if all volcanoes erupted at once?", "Ash, sunlight, flights, crops, and breathing become one visual disaster.", ["what if", "volcano", "earth", "ash", "survival"]),
        _seed("What if a black hole passed near Earth?", "A near miss that pulls tides, orbits, and fear into one hook.", ["what if", "black hole", "earth", "gravity", "tides"]),
        _seed("What if Earth had no atmosphere for 10 seconds?", "Show silence, pressure loss, sky color, and exposed oceans fast.", ["what if", "earth", "atmosphere", "body", "ocean"]),
        _seed("What if the oceans boiled for one minute?", "A surreal steam-world scene with coastlines and weather changing instantly.", ["what if", "ocean", "earth", "steam", "disaster"]),
        _seed("What if the Moon moved twice as close?", "Giant tides, brighter nights, and orbital tension are visible right away.", ["what if", "moon", "earth", "tides", "gravity"]),
        _seed("What if Earth shrank by half overnight?", "Gravity, oceans, buildings, and bodies all change in one impossible morning.", ["what if", "earth", "gravity", "body", "ocean"]),
        _seed("What if the Sun became twice as bright?", "A heat, crop, ocean, and sky-color disaster in five quick beats.", ["what if", "sun", "heat", "earth", "survival"]),
        _seed("What if every cloud fell at once?", "Turn water weight into floods, impact, dark skies, and shock visuals.", ["what if", "clouds", "flood", "earth", "storm"]),
        _seed("What if Earth spun backward for one day?", "Use winds, oceans, sunrise, and confusion as visible consequences.", ["what if", "earth", "time", "ocean", "storm"]),
        _seed("What if an asteroid hit the ocean?", "A wave-first disaster with steam, impact, coastlines, and dark skies.", ["what if", "asteroid", "ocean", "earth", "tsunami"]),
        _seed("What if humans stopped needing sleep?", "A body-and-city scenario with time, exhaustion, work, and biology tension.", ["what if", "humans", "body", "time", "survival"]),
        _seed("What if Earth's core cooled instantly?", "Magnetic field, volcanoes, continents, and survival all become visible.", ["what if", "earth", "core", "magnetic field", "volcano"]),
        _seed("What if gravity turned off for 5 seconds?", "People, oceans, air, and debris lift before gravity returns.", ["what if", "gravity", "earth", "body", "ocean"]),
        _seed("What if the Sun went red for one day?", "A strange sky, heat shift, plant stress, and fear hook in seconds.", ["what if", "sun", "earth", "sky", "survival"]),
        _seed("What if every iceberg melted overnight?", "Sea-level shock, maps, cities, and coastlines make the danger visible.", ["what if", "iceberg", "ocean", "earth", "flood"]),
        _seed("What if Earth's air became twice as dense?", "Breathing, flight, weather, and sound change in an easy visual sequence.", ["what if", "earth", "air", "body", "storm"]),
        _seed("What if the Moon cracked in half?", "A giant sky image with tides, debris, and orbital consequences.", ["what if", "moon", "earth", "tides", "disaster"]),
        _seed("What if a solar storm hit every power grid?", "Cities going dark gives an instant non-follower hook.", ["what if", "sun", "storm", "earth", "city"]),
        _seed("What if Earth lost oxygen for one breath?", "A shorter body-first hook about lungs, fire, and sky changes.", ["what if", "oxygen", "body", "fire", "earth"]),
        _seed("What if the oceans turned fresh overnight?", "Marine life, currents, weather, and food chains become visible fast.", ["what if", "ocean", "earth", "survival", "weather"]),
        _seed("What if the sky turned black at noon?", "A clear first-second image with sun, atmosphere, panic, and cold.", ["what if", "sun", "sky", "earth", "dark"]),
        _seed("What if Earth's gravity pulsed every hour?", "A visual rhythm of falling, lifting, waves, and broken infrastructure.", ["what if", "gravity", "earth", "body", "ocean"]),
        _seed("What if every earthquake happened at once?", "A global ground-shaking visual that can be explained as a sharp chain.", ["what if", "earthquake", "earth", "city", "disaster"]),
    ],
    "extreme_science": [
        _seed("A planet where it may rain glass", "Alien weather turns into a sharp visual science story.", ["planet", "glass rain", "extreme", "space"]),
        _seed("A star so dense a spoonful weighs billions of tons", "Neutron-star density makes real physics feel impossible.", ["star", "neutron star", "gravity", "extreme"]),
        _seed("A storm bigger than Earth", "Jupiter's giant storm gives instant scale and motion.", ["storm", "planet", "Jupiter", "earth"]),
        _seed("A black hole tearing a star apart", "Tidal disruption is violent, visual, and real.", ["black hole", "star", "gravity", "extreme"]),
        _seed("Rogue planets drifting without a star", "A frozen world with no sunrise makes space feel lonely and unreal.", ["rogue planet", "planet", "star", "space"]),
        _seed("A moon with an ocean under ice", "Hidden oceans under frozen crust create a strong reveal.", ["moon", "ocean", "ice", "space"]),
        _seed("A planet darker than coal", "A nearly light-eating world makes darkness the hook.", ["planet", "dark", "space", "extreme"]),
        _seed("A planet with diamond rain", "High pressure turns weather into an impossible-feeling image.", ["planet", "diamond rain", "storm", "extreme"]),
        _seed("A place where time runs differently", "Gravity and speed become visible through clocks and light.", ["time", "gravity", "black hole", "extreme"]),
        _seed("A star that spins hundreds of times per second", "A tiny dead star becomes a cosmic blender.", ["star", "neutron star", "time", "extreme"]),
        _seed("A planet made almost entirely of ocean", "A water world makes scale easy for cold audiences.", ["planet", "ocean", "space", "extreme"]),
        _seed("A moon with volcanoes taller than nightmares", "Io-style eruptions make a moon feel alive and dangerous.", ["moon", "volcano", "space", "extreme"]),
        _seed("A planet with winds faster than sound", "Invisible wind becomes a cinematic survival problem.", ["planet", "storm", "wind", "extreme"]),
        _seed("A star escaping the galaxy", "A runaway star turns space motion into a visual chase.", ["star", "galaxy", "speed", "space"]),
        _seed("A black hole with a shadow wider than our solar system", "Scale becomes the hook before the explanation starts.", ["black hole", "shadow", "solar system", "space"]),
        _seed("A planet orbiting two suns", "Double sunsets are clear, cinematic, and science-backed.", ["planet", "sun", "star", "space"]),
        _seed("A moon where geysers blast into space", "Water jets from ice make hidden oceans visible.", ["moon", "ice", "ocean", "space"]),
        _seed("A star that could fit inside a city", "Small size plus impossible mass creates instant curiosity.", ["star", "neutron star", "gravity", "city"]),
        _seed("A planet hotter than some stars", "Heat, lava, and glowing skies create immediate visual shock.", ["planet", "star", "heat", "extreme"]),
        _seed("A galaxy collision happening in slow motion", "Huge scale and slow time make a strong retention arc.", ["galaxy", "collision", "time", "space"]),
        _seed("A cloud where stars are being born", "Nebula birth scenes are visual and easy to explain.", ["star", "nebula", "space", "extreme"]),
        _seed("A planet where metal may fall as rain", "Metal weather is simple, strange, and image-friendly.", ["planet", "rain", "metal", "extreme"]),
        _seed("A black hole that shoots jets across space", "Energy beams make invisible gravity visually dramatic.", ["black hole", "jet", "space", "gravity"]),
        _seed("A world where one side never sees daylight", "Tidally locked planets make a clear day-night split.", ["planet", "star", "dark", "time"]),
        _seed("A moon that looks like a giant cracked egg", "A strange surface becomes a fast visual hook.", ["moon", "ice", "space", "surface"]),
        _seed("A planet with lava oceans", "Lava seas make exoplanet heat instantly understandable.", ["planet", "lava", "ocean", "extreme"]),
        _seed("A star dying in a supernova", "A cosmic explosion creates high visual shock and clear stakes.", ["star", "supernova", "explosion", "space"]),
        _seed("A planet stretched by its star's gravity", "Tidal forces turn a round world into a distorted image.", ["planet", "star", "gravity", "extreme"]),
        _seed("A cosmic void bigger than imagination", "Empty space becomes a scale hook with a simple reveal.", ["space", "void", "galaxy", "scale"]),
        _seed("A moon with lakes of methane", "Alien lakes make a familiar landscape feel unreal.", ["moon", "lake", "methane", "space"]),
    ],
    "future_scenario": [
        _seed("What if humans lived on Mars for 100 years?", "A century of bodies, cities, food, and culture adapting to Mars.", ["what if", "humans", "Mars", "future", "city"]),
        _seed("What if AI controlled city traffic?", "A visible city system where every light reacts in real time.", ["what if", "AI", "city", "traffic", "future"]),
        _seed("What if schools had AI teachers?", "Classrooms change through personalization, attention, and trust.", ["what if", "AI", "schools", "future", "humans"]),
        _seed("What if cities had no human drivers?", "Streets, parking, crashes, and commutes change in one future loop.", ["what if", "city", "drivers", "AI", "future"]),
        _seed("What if work became optional?", "Money, identity, time, and boredom become the story.", ["what if", "work", "time", "future", "humans"]),
        _seed("What if robots built entire cities?", "Construction becomes a visual swarm of machines and new skylines.", ["what if", "robots", "city", "future", "construction"]),
        _seed("What if humans had personal AI doctors?", "A pocket doctor changes diagnosis, panic, and hospital visits.", ["what if", "AI", "doctor", "body", "future"]),
        _seed("What if every home had a robot helper?", "Domestic automation creates visual, relatable future stakes.", ["what if", "robot", "home", "future", "humans"]),
        _seed("What if Mars had its first child?", "A body, gravity, identity, and society scenario in one hook.", ["what if", "Mars", "humans", "body", "future"]),
        _seed("What if cities moved underground?", "Heat, storms, daylight, and architecture become visible consequences.", ["what if", "city", "underground", "future", "survival"]),
        _seed("What if oceans had floating cities?", "A clear visual future with storms, food, and survival questions.", ["what if", "ocean", "city", "future", "survival"]),
        _seed("What if people lived to 150?", "Family, work, memory, and medicine change fast.", ["what if", "humans", "body", "future", "time"]),
        _seed("What if food was grown in skyscrapers?", "Vertical farms make cities, water, and diets visual.", ["what if", "food", "city", "future", "farm"]),
        _seed("What if humans mined the Moon?", "A lunar worksite makes space economics visible without politics.", ["what if", "moon", "humans", "future", "space"]),
        _seed("What if AI predicted disasters before they happened?", "Storms, fires, evacuations, and trust create a tight chain.", ["what if", "AI", "disaster", "future", "survival"]),
        _seed("What if delivery drones filled the sky?", "A relatable sky-change story with noise, speed, and safety.", ["what if", "drones", "city", "future", "sky"]),
        _seed("What if nobody owned cars anymore?", "Parking lots, streets, and city design shift visually.", ["what if", "cars", "city", "future", "drivers"]),
        _seed("What if humans had digital memory backups?", "Identity, grief, memory, and risk create a strong curiosity gap.", ["what if", "humans", "memory", "future", "AI"]),
        _seed("What if hospitals used robot surgeons everywhere?", "A high-stakes body and trust scenario with clear visuals.", ["what if", "robots", "doctor", "body", "future"]),
        _seed("What if farms moved into the ocean?", "Food systems become underwater, stormy, and visual.", ["what if", "ocean", "food", "future", "farm"]),
        _seed("What if space hotels became normal?", "A luxury future with gravity, windows, and hidden risks.", ["what if", "space", "hotel", "future", "gravity"]),
        _seed("What if cities banned private cars?", "Streets, walking, deliveries, and emergency access become visual.", ["what if", "city", "cars", "future", "traffic"]),
        _seed("What if every person had an AI clone?", "A social future about work, messages, identity, and trust.", ["what if", "AI", "humans", "future", "identity"]),
        _seed("What if humans lived in orbital cities?", "Gravity, windows, sunlight, and danger make the future cinematic.", ["what if", "humans", "city", "space", "future"]),
        _seed("What if classrooms had no textbooks?", "Screens, AI tutors, memory, and attention make a fast scenario.", ["what if", "schools", "AI", "future", "learning"]),
        _seed("What if clothes adjusted to weather automatically?", "Wearable tech creates immediate body-level future visuals.", ["what if", "body", "weather", "future", "technology"]),
        _seed("What if cities had giant shade shields?", "Heat survival, architecture, and sunlight become visually clear.", ["what if", "city", "sun", "future", "survival"]),
        _seed("What if humans could hibernate for space travel?", "Body, time, Mars, and survival create a strong Reel chain.", ["what if", "humans", "body", "time", "space"]),
        _seed("What if AI ran emergency rooms?", "Urgency, triage, trust, and speed turn AI into a visible scenario.", ["what if", "AI", "doctor", "body", "future"]),
        _seed("What if robots repaired roads overnight?", "A city visibly heals while people sleep.", ["what if", "robots", "city", "future", "roads"]),
    ],
}


LEGACY_SEED_TOPICS: dict[str, list[dict[str, object]]] = {
    "history": [
        _seed("Ancient Rome daily life", "Make the empire personal through food, streets, baths, and work.", ["ancient", "Rome", "daily life", "empire"], lane="any"),
        _seed("The Black Death doctor mask", "Explain the strange beaked mask through fear, medicine, and myth.", ["Black Death", "doctor mask", "medieval", "strange detail"], lane="any"),
        _seed("Life inside a medieval castle", "Show survival, status, and daily routines inside stone walls.", ["medieval", "castle", "daily life", "survival"], lane="any"),
        _seed("The last night on the Titanic", "Use a final-night timeline to build emotion and suspense.", ["Titanic", "last night", "disaster", "history"], lane="any"),
        _seed("Ancient Egyptian daily life", "Go beyond pyramids into homes, bread, work, and belief.", ["ancient", "Egyptian", "daily life", "history"], lane="any"),
    ]
}


class StaticSeedSource(DiscoverySource):
    name = "static"

    def fetch(
        self,
        niche: str,
        count: int,
        query: str | None = None,
        lane: DiscoveryLane = "any",
    ) -> list[TopicCandidate]:
        rows = _rows_for(niche=niche, lane=lane)
        if query:
            query_lower = query.lower()
            filtered = [
                row
                for row in rows
                if query_lower in str(row["topic"]).lower()
                or query_lower in str(row["angle"]).lower()
                or any(query_lower in str(keyword).lower() for keyword in row["keywords"])
            ]
            rows = filtered or rows

        candidates: list[TopicCandidate] = []
        for row in rows[: max(count, 1)]:
            row_lane = str(row.get("lane") or lane)
            candidates.append(
                TopicCandidate(
                    topic=str(row["topic"]),
                    niche=niche,
                    lane=row_lane if row_lane in LANE_SEED_TOPICS else "any",
                    angle=str(row["angle"]),
                    source=self.name,
                    source_title=str(row["topic"]),
                    source_summary=str(row["angle"]),
                    keywords=[str(keyword) for keyword in row["keywords"]],
                    reasons=["Local evergreen seed topic."],
                )
            )
        return candidates


def _rows_for(niche: str, lane: DiscoveryLane) -> list[dict[str, object]]:
    normalized_niche = niche.lower()
    if normalized_niche == "history":
        return LEGACY_SEED_TOPICS["history"]
    if lane != "any":
        return [
            {**row, "lane": lane}
            for row in LANE_SEED_TOPICS[lane]
        ]

    rows: list[dict[str, object]] = []
    lanes = ["what_if_disaster", "extreme_science", "future_scenario"]
    max_len = max(len(LANE_SEED_TOPICS[item]) for item in lanes)
    for index in range(max_len):
        for item in lanes:
            lane_rows = LANE_SEED_TOPICS[item]
            if index < len(lane_rows):
                rows.append({**lane_rows[index], "lane": item})
    return rows
