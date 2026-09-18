"""AI Analyst: a quick auto-loading per-state card, and a separately
triggered, longer national/state briefing.

Per design: both endpoints look across ALL 3 tracked pathogens (not just
whichever is selected on the map toggle) plus WHO DON's emerging-threat
content -- the AI's job is to notice whatever's actually notable anywhere in
the data, not describe a fixed per-pathogen template regardless of whether
anything in it is worth mentioning.
"""

import json
import os
from datetime import datetime, timedelta

import anthropic
from fastapi import APIRouter, HTTPException

from api.map import build_states_payload, map_outbreak_alerts
from db import get_connection

router = APIRouter()

STATE_CARD_TTL = timedelta(hours=1)
BRIEFING_TTL = timedelta(hours=6)

# Fast/cheap for the auto-loading card (fires on every state click);
# higher-quality for the deliberately-triggered briefing. Easy to change.
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-5"

# Web search is only wired into /api/ai/briefing (deliberately triggered),
# not the auto-loading state card -- it adds real latency and per-search
# cost, which is fine for a button click but not for something that fires
# on every map interaction. Restricted to authoritative health/news sources
# so a "biothreat radar" briefing doesn't end up citing random blogs.
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
    # apnews.com and reuters.com were tried and rejected by the API --
    # "not accessible to our user agent" (their crawler is blocked there).
    # Confirmed working: the sources below.
    "allowed_domains": [
        "cdc.gov", "who.int", "ecdc.europa.eu", "promedmail.org",
        "gov.uk", "outbreaknewstoday.com",
    ],
}

SYSTEM_PROMPT = (
    "You are an analyst for a CDC biothreat radar program, synthesizing "
    "wastewater, syndromic, and genomic surveillance data plus global "
    "outbreak alerts. Your job is to notice whatever is ACTUALLY notable or "
    "worth flagging -- do not walk through every pathogen as a fixed "
    "template if there's nothing unusual about it. A precise reading from an "
    "otherwise-quiet source is not itself news; it's fine, and often "
    "correct, to say nothing unusual is happening. Prioritize: sudden spikes "
    "or 'Very High' wastewater categories, rising trends, a variant gaining "
    "share fast, and any global emerging-threat alert (Ebola, Nipah, "
    "Hantavirus, Yellow Fever, etc.) that has no US domestic tracking at all "
    "-- those are the actual emerging-threat signals, not routine seasonal "
    "COVID/flu/RSV levels. Be concrete: name states, pathogens, and numbers. "
    "Do not hedge with vague language like 'may be of interest.' When you "
    "have web search available and use it, name the specific source (e.g. "
    "'per WHO' or 'per CDC') for anything you cite from search, and clearly "
    "distinguish it from the loaded structured data."
)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _extract_text(content_blocks) -> str:
    """Concatenate all text blocks in a response. Needed once web search is
    enabled -- the content list then also contains server_tool_use and
    web_search_tool_result blocks interleaved with text, so grabbing
    content[0].text alone would silently truncate or grab the wrong block.
    """
    return "".join(getattr(block, "text", "") for block in content_blocks if getattr(block, "type", None) == "text")


def _get_cached(con, cache_key: str, ttl: timedelta) -> tuple[str, datetime] | None:
    row = con.execute(
        "SELECT content, generated_at FROM ai_narrative_cache WHERE cache_key = ?", [cache_key]
    ).fetchone()
    if not row:
        return None
    content, generated_at = row
    if datetime.now() - generated_at > ttl:
        return None
    return content, generated_at


def _set_cache(con, cache_key: str, kind: str, content: str, model: str, data_snapshot: dict) -> datetime:
    now = datetime.now()
    existing = con.execute("SELECT 1 FROM ai_narrative_cache WHERE cache_key = ?", [cache_key]).fetchone()
    if existing:
        con.execute(
            """UPDATE ai_narrative_cache
               SET content = ?, model = ?, generated_at = ?, data_snapshot = ?
               WHERE cache_key = ?""",
            [content, model, now, json.dumps(data_snapshot), cache_key],
        )
    else:
        con.execute(
            """INSERT INTO ai_narrative_cache (cache_key, kind, content, model, generated_at, data_snapshot)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [cache_key, kind, content, model, now, json.dumps(data_snapshot)],
        )
    return now


def _format_state_signals(state_name: str, signals: dict) -> str:
    lines = [f"=== {state_name} ==="]

    lines.append("Wastewater (viral activity category across all reporting sites, by pathogen):")
    for pathogen, w in signals.get("wastewater", {}).items():
        dist = ", ".join(f"{k}: {v}" for k, v in w["category_distribution"].items())
        lines.append(f"  {pathogen}: {dist} (n={w['site_count']} sites, trend={w['trend']}, as of {w['period_end']})")

    lines.append("Syndromic (% of ED visits, by pathogen):")
    for pathogen, s in signals.get("syndromic", {}).items():
        lines.append(f"  {pathogen}: {s['percent_ed_visits']}% (CDC trend: {s.get('trend') or 'unavailable'}, as of {s['period_end']})")

    genomic = signals.get("genomic")
    if genomic:
        lines.append("Genomic (SARS-CoV-2 lineages only -- shared across this state's HHS region):")
        leader = genomic["current_leader"]
        lines.append(f"  Current leader: {leader['variant']} ({leader['share'] * 100:.0f}% share)")
        fg = genomic.get("fastest_growing")
        if fg:
            lines.append(f"  Fastest growing: {fg['variant']} ({fg['share'] * 100:.0f}% share, "
                          f"+{fg['change'] * 100:.1f} points vs. prior period)")
        lines.append(f"  As of {genomic['period_end']}")

    return "\n".join(lines)


def _national_summary(payload: dict) -> str:
    lines = ["=== National summary (pre-filtered to notable states -- full data not included) ==="]

    high_ww = []
    for state, sig in payload.items():
        for pathogen, w in sig.get("wastewater", {}).items():
            very_high = w["category_distribution"].get("Very High", 0)
            if very_high > 0:
                high_ww.append(f"{state} ({pathogen}: {very_high} of {w['site_count']} sites Very High, trend {w['trend']})")
    lines.append("States with wastewater sites at 'Very High' viral activity:")
    lines += [f"  - {s}" for s in high_ww[:25]] if high_ww else ["  (none)"]

    increasing = []
    for state, sig in payload.items():
        for pathogen, s in sig.get("syndromic", {}).items():
            trend = (s.get("trend") or "").lower()
            if "increas" in trend:
                increasing.append(f"{state} ({pathogen}: {s['percent_ed_visits']}% ED visits)")
    lines.append("States with syndromic trend 'Increasing':")
    lines += [f"  - {s}" for s in increasing[:25]] if increasing else ["  (none)"]

    fastest: dict[str, dict] = {}
    for sig in payload.values():
        genomic = sig.get("genomic")
        fg = genomic.get("fastest_growing") if genomic else None
        if fg and (fg["variant"] not in fastest or fg["change"] > fastest[fg["variant"]]["change"]):
            fastest[fg["variant"]] = fg
    if fastest:
        top = max(fastest.values(), key=lambda x: x["change"])
        lines.append(f"Nationally fastest-growing SARS-CoV-2 variant: {top['variant']} "
                      f"({top['share'] * 100:.0f}% share, +{top['change'] * 100:.1f} points)")

    return "\n".join(lines)


def _who_don_context(limit: int = 8) -> str:
    data = map_outbreak_alerts(limit=limit)
    lines = ["=== Recent global emerging-threat alerts (WHO Disease Outbreak News) ==="]
    for a in data["alerts"]:
        lines.append(f"  - {a['country']} ({a['pathogen'] or 'unspecified pathogen'}, {a['date']}): {a['title']}")
        if a.get("excerpt"):
            lines.append(f"    {a['excerpt']}")
    return "\n".join(lines)


@router.get("/api/ai/state-card")
def state_card(state: str, regenerate: bool = False):
    con = get_connection()
    cache_key = f"state-card:{state}"

    if not regenerate:
        cached = _get_cached(con, cache_key, STATE_CARD_TTL)
        if cached:
            content, generated_at = cached
            return {"state": state, "content": content, "generated_at": generated_at.isoformat(), "cached": True}

    payload = build_states_payload(con)
    signals = payload.get(state)
    if signals is None:
        raise HTTPException(status_code=404, detail=f"No data for state '{state}'")

    prompt = (
        f"{_format_state_signals(state, signals)}\n\n{_who_don_context()}\n\n"
        f"In 2-4 sentences, give a plain-English takeaway for {state}. Highlight whatever's "
        "actually notable across wastewater, syndromic, or genomic data. Mention a global "
        "alert only if genuinely relevant to this state's risk profile (e.g. international "
        "travel exposure) -- don't force a connection that isn't there."
    )

    message = _get_client().messages.create(
        model=HAIKU_MODEL, max_tokens=300, system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    content = _extract_text(message.content)

    generated_at = _set_cache(con, cache_key, "state_card", content, HAIKU_MODEL, {"state": state})
    return {"state": state, "content": content, "generated_at": generated_at.isoformat(), "cached": False}


@router.get("/api/ai/briefing")
def briefing(state: str | None = None, regenerate: bool = False):
    con = get_connection()
    scope = state or "national"
    cache_key = f"briefing:{scope}"

    if not regenerate:
        cached = _get_cached(con, cache_key, BRIEFING_TTL)
        if cached:
            content, generated_at = cached
            return {"scope": scope, "content": content, "generated_at": generated_at.isoformat(), "cached": True}

    payload = build_states_payload(con)

    # Lead with external/global alerts, domestic surveillance second: per
    # explicit direction, the wastewater/syndromic/genomic numbers are
    # already visible on the map and state panels elsewhere in the app --
    # the briefing's actual unique value is the threat intelligence that
    # ISN'T easy to find elsewhere (global alerts, live search findings).
    if state:
        signals = payload.get(state)
        if signals is None:
            raise HTTPException(status_code=404, detail=f"No data for state '{state}'")
        data_context = _format_state_signals(state, signals)
        scope_instruction = (
            f"Structure this briefing on {state} in two sections, IN THIS ORDER:\n\n"
            f"1. RELEVANT EXTERNAL ALERTS (lead with this, most substantial section): use "
            f"web search to check for any current, state-specific health department alerts "
            f"for {state}, or global emerging threats with genuine relevance to {state} "
            "(e.g. via its international travel connections) that aren't already covered by "
            "the data below. This comes first because it's not easy to find elsewhere in "
            "this application. If nothing new or relevant turns up, say so briefly rather "
            "than forcing a connection.\n\n"
            f"2. DOMESTIC SURVEILLANCE SUMMARY (brief, comes second): a concise summary of "
            f"{state}'s wastewater, syndromic, and genomic trends from the data below. Keep "
            "this shorter -- the underlying numbers are already visible on the map and state "
            "panel, so don't just restate every figure.\n\n"
            "Name specific sources when citing search results. Be specific, avoid generic filler."
        )
    else:
        data_context = _national_summary(payload)
        scope_instruction = (
            "Structure this national briefing in two sections, IN THIS ORDER:\n\n"
            "1. GLOBAL & EMERGING THREATS (lead with this, most substantial section): use web "
            "search to find CURRENT emerging or re-emerging biothreats worldwide -- new "
            "outbreaks, novel pathogens, biosecurity incidents, significant recent "
            "developments -- that are NOT already covered by the WHO DON alerts below (which "
            "may be several days old). Combine this with the WHO DON alerts themselves. This "
            "comes first because domestic surveillance numbers are already visible elsewhere "
            "in this application -- your job here is real-time global threat intelligence "
            "that isn't easy to find elsewhere.\n\n"
            "2. DOMESTIC SURVEILLANCE SUMMARY (brief, comes second): a shorter summary of "
            "anything notable in the wastewater/syndromic/genomic data below -- worsening "
            "categories, rising trends, fast-growing variants. Keep this concise -- the "
            "underlying numbers are already visible on the map and state panels.\n\n"
            "This is for a CDC audience: be specific, avoid generic filler, and name specific "
            "sources when citing search results."
        )

    # WHO DON context first, matching the desired output order above.
    prompt = f"{_who_don_context(limit=12)}\n\n{data_context}\n\n{scope_instruction}"

    message = _get_client().messages.create(
        # 16000 confirmed necessary, not just generous: at 2000 (the original
        # limit) and even 8000, a 5-search national briefing hit
        # stop_reason="max_tokens" and got cut off mid-response -- search
        # results + reasoning consume a lot of the output budget before the
        # model even starts writing the final synthesis. Verified 16000
        # completes with stop_reason="end_turn" and room to spare.
        model=SONNET_MODEL, max_tokens=16000, system=SYSTEM_PROMPT,
        tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": prompt}],
    )
    content = _extract_text(message.content)
    truncated = message.stop_reason == "max_tokens"
    if truncated:
        # Don't fail silently -- this happened once already at a lower limit
        # and produced a briefing that quietly dropped the global-alerts
        # section. Log it so a recurrence is visible instead of just "the
        # briefing seemed a bit short again."
        print(f"[ai.briefing] WARNING: response for scope={scope!r} was cut off "
              f"(stop_reason=max_tokens) despite a 16000 token budget. "
              f"output_tokens={message.usage.output_tokens}")
        content += "\n\n*(Note: this response was cut off before completion. Try regenerating.)*"

    generated_at = _set_cache(con, cache_key, "briefing", content, SONNET_MODEL,
                               {"scope": scope, "web_search_enabled": True, "truncated": truncated})
    return {"scope": scope, "content": content, "generated_at": generated_at.isoformat(), "cached": False}
