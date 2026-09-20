"""The label taxonomy in one place, so the guide and the API schema can never disagree.

The human-readable definitions live in prompts/labeling_guide.md, which is sent to the
model verbatim. The machine-readable enums live here and are sent as a strict JSON
schema. `check_guide()` asserts that every value here appears in the guide, so editing
one without the other fails loudly instead of producing silently wrong labels.

FROZEN once a labeling run starts: changing a value changes the labels, so a run that
mixes two versions is not analysable. Bump TAXONOMY_VERSION if you must change one.
"""
from pathlib import Path

TAXONOMY_VERSION = "1.1"

GUIDE_PATH = Path(__file__).resolve().parents[1] / "prompts" / "labeling_guide.md"

TOPICS = [
    "affordability_access", "grey_market", "telehealth_rx", "marketing_promo",
    "side_effects_safety", "medical_condition", "personal_experience",
    "cosmetic_vanity_use", "weight_loss_results", "celebrity_watch",
    "culture_war_body", "eating_disorder", "appearance_commentary", "politics_policy",
    "pharma_industry_critique", "finance_investing", "science_news",
    "conspiracy_misinfo", "humor_meme", "dating_sexual", "religion_morality",
    "fitness_muscle", "food_industry", "off_label_use", "spam_irrelevant",
]

DRUGS = [
    # GLP-1 brands and the molecules behind them
    "ozempic", "wegovy", "semaglutide", "mounjaro", "zepbound", "tirzepatide",
    "retatrutide", "saxenda", "victoza", "liraglutide", "trulicity", "dulaglutide",
    # oral forms
    "rybelsus", "orforglipron", "oral_glp1",
    # investigational and non-GLP-1 peptides
    "survodutide", "cagrilintide", "other_peptide",
    # catch-alls
    "glp1_generic", "unspecified",
]

INTENTS = [
    "share_experience", "seek_info", "give_advice", "inform_news", "promote_sell",
    "joke", "opinion_argue", "criticize_attack", "praise_endorse", "gossip_speculate",
    "vent", "other",
]

EMOTIONS = [
    "joking", "sarcastic", "argumentative", "agreeing", "praising", "angry",
    "disgusted", "anxious_fearful", "sad_defeated", "hopeful_excited",
    "envious_resentful", "shaming_mocking", "supportive_empathetic", "defensive",
    "neutral_factual",
]

STANCES = ["strongly_positive", "positive", "mixed", "neutral", "negative",
           "strongly_negative", "unclear"]

SPEAKERS = ["current_user", "former_user", "prospective_user", "caregiver_proxy",
            "health_professional", "seller_vendor", "observer_commentator", "unclear"]

RISKS = ["grey_market_sourcing", "vendor_solicitation", "unverified_dosing_advice",
         "eating_disorder_signal", "self_harm_signal", "medical_misinformation",
         "minor_involved", "hateful_content"]

CONFIDENCE = ["high", "medium", "low"]

# field -> (kind, allowed values). "one" = single string, "many" = array of strings.
FIELDS = {
    "topics": ("many", TOPICS),
    "drugs": ("many", DRUGS),
    "intent": ("one", INTENTS),
    "emotions": ("many", EMOTIONS),
    "stance": ("one", STANCES),
    "speaker": ("one", SPEAKERS),
    "risks": ("many", RISKS),
    "named": ("free", None),
    "confidence": ("one", CONFIDENCE),
}

LABEL_KEYS = ["id"] + list(FIELDS)


def label_schema() -> dict:
    """The strict JSON schema sent as response_format.

    No minItems/maxItems: strict mode does not enforce them, so the counts are stated in
    the guide and checked in code instead.
    """
    props = {"id": {"type": "integer"}}
    for field, (kind, values) in FIELDS.items():
        if kind == "one":
            props[field] = {"type": "string", "enum": list(values)}
        elif kind == "many":
            props[field] = {"type": "array", "items": {"type": "string", "enum": list(values)}}
        else:
            props[field] = {"type": "array", "items": {"type": "string"}}
    item = {"type": "object", "properties": props,
            "required": LABEL_KEYS, "additionalProperties": False}
    return {
        "type": "object",
        "properties": {"labels": {"type": "array", "items": item}},
        "required": ["labels"],
        "additionalProperties": False,
    }


def check_guide() -> None:
    """Every enum value must appear in the guide, or the two have drifted apart."""
    if not GUIDE_PATH.exists():
        raise SystemExit(f"missing guide: {GUIDE_PATH}")
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    missing = [v for _, values in FIELDS.values() if values for v in values if v not in guide]
    if missing:
        raise SystemExit(
            "These taxonomy values are not documented in prompts/labeling_guide.md:\n  "
            + "\n  ".join(missing)
            + "\nAdd them to the guide, or remove them here. The model only ever sees the guide."
        )


def validate(label: dict) -> list[str]:
    """Problems with one returned label. Empty list means it is well formed."""
    problems = []
    for key in LABEL_KEYS:
        if key not in label:
            problems.append(f"missing {key}")
    for field, (kind, values) in FIELDS.items():
        got = label.get(field)
        if kind == "free":
            continue
        if kind == "one":
            if got not in values:
                problems.append(f"{field}={got!r} not allowed")
        else:
            if not isinstance(got, list):
                problems.append(f"{field} is not a list")
            else:
                problems += [f"{field} has {v!r}" for v in got if v not in values]
    if isinstance(label.get("topics"), list) and not 1 <= len(label["topics"]) <= 4:
        problems.append(f"topics has {len(label['topics'])} entries, want 1-4")
    if isinstance(label.get("emotions"), list) and not 1 <= len(label["emotions"]) <= 3:
        problems.append(f"emotions has {len(label['emotions'])} entries, want 1-3")
    return problems


if __name__ == "__main__":
    check_guide()
    counts = {f: len(v) for f, (_, v) in FIELDS.items() if v}
    print(f"taxonomy v{TAXONOMY_VERSION}: guide and schema agree")
    for f, n in counts.items():
        print(f"  {f:12} {n:3} values")
    print(f"  {'named':12}   free text")
    print(f"\nguide: {GUIDE_PATH.stat().st_size:,} bytes (~{GUIDE_PATH.stat().st_size // 4:,} tokens)")
