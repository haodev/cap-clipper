"""The topic definition in one place, so the extract and the dataset always agree.

FROZEN: these terms define the published dataset. Changing them changes the dataset, so
the extract must then be rerun from scratch and every count in DATASET.md re-checked.
Add a spelling only if it is a major omission, not for completeness.

Two rules that caused wrong counts before:
  - a hyphen can be a normal "-" or one of several unicode dashes, and people also write "GLP 1"
  - a drug name inside a link (https://t.co/dNVNWGlP1i) or a username (@OzempicPigMan) is not
    the tweet being about the drug, so matching is done on the text with those removed
"""
import pandas as pd

DASHES = "‐‑‒–—−"   # the unicode hyphens people paste in
SEP = f"[ _.{DASHES}-]?"   # optional separator: space, underscore, dot or any dash.
                           # The plain "-" must stay last, or the regex reads it as a range.

# Each drug: the spellings people actually use, including other languages.
DRUGS = {
    "ozempic": r"ozempi[ck]|ozempc|ozempik",
    "wegovy": r"wegov[yi]",
    "semaglutide": r"semaglutid[ea]",
    "mounjaro": r"mounjaro|munjaro",
    "zepbound": r"zepbound",
    "tirzepatide": r"tirzepatid[ea]",
    "retatrutide": r"retatrutid[ea]",
    # glp-1, glp 1, glp1, plus the plural and the medical forms glp-1ra / glp-1r
    "glp1": rf"\bglp{SEP}1(?:ra|rs|r|s)?\b",
    "weight_loss_drug": rf"weight{SEP}loss (?:drug|jab|shot|injection|med|medication)s?",
}

ANY_DRUG = "|".join(f"(?:{p})" for p in DRUGS.values())


def text_only(body: pd.Series) -> pd.Series:
    """Lowercase text with links and @usernames removed: what the tweet actually says."""
    return (body.str.lower()
            .str.replace(r"https?://\S+", " ", regex=True)
            .str.replace(r"@\w+", " ", regex=True))


def links_only(body: pd.Series) -> pd.Series:
    return body.str.lower().str.findall(r"https?://\S+").str.join(" ")


def usernames_only(body: pd.Series) -> pd.Series:
    return body.str.lower().str.findall(r"@\w+").str.join(" ")
