"""Pick the most specific domain card for an identification result.

    exact version known  -> that model's full card                 (level "version")
    only the family      -> family-level fields of its known models (level "family"), if the line has at
                            least 2 known versions; otherwise the developer card (see below)
    only the developer   -> family-level fields of all its models   (level "developer")
    nothing known        -> no card                                 (level "none")

Why 2 versions: the version is Unknown because the chatbot didn't fit any known version. If the line has only one
known version, that one version didn't fit, so nothing shows the chatbot is really in that line rather than another
line from the same developer (e.g. a hidden Claude Haiku is judged "Claude Sonnet, version Unknown"). The developer
card is the safe choice there; for a developer with one line (Meta, Alibaba) it holds the same fields anyway.

Family and developer cards only show fields marked `level: family` in cards/fields/*.yaml (they hold for every
model in the group), and say which model each value comes from. A value shared by every model in the group is
marked `same_for_all`; otherwise the card lists the possible values.

    from card_lookup import lookup_card
    card = lookup_card(version_key="llama3.1-8b")
    card = lookup_card(family="Llama")                 # version Unknown
    card = lookup_card(developer="Google")             # family Unknown
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cards"))
from cardlib import DOMAINS, _domain_card, build_card, card_models, load_card, load_fields  # noqa: E402
from identify import DEVELOPER, MODELS  # noqa: E402

LEVELS = ["version", "family", "developer", "none"]
MIN_FAMILY_MODELS = 2      # known versions a line needs before its family card is used


def _members(test, known):
    """Models that have cards, pass the test, and are known (not hidden)."""
    return [k for k in card_models() if k in MODELS and test(k) and (known is None or k in known)]


def _group_card(level, label, members, domains, why=""):
    out = {"level": level, "label": label, "model_key": None, "confirmed": False, "known_models": members,
           "note": f"{'Version' if level == 'family' else 'Family and version'} unknown{why}. Showing the fields "
                   f"that hold for every model in this {level}, taken from its known models: possible obligations, "
                   f"not confirmed for the deployed model.", "domains": []}
    for d in domains:
        spec, fields = load_fields(d), []
        for f in spec["fields"]:
            if f["level"] != "family" or f["filled_by"] in ("organization", "system"):
                continue
            values = []
            for k in members:
                entry = next(e for e in _domain_card(d, k)["fields"] if e["id"] == f["id"])
                if entry.get("missing"):
                    continue
                same = next((v for v in values if v["value"] == entry["value"]), None)
                if same:
                    same["from_models"].append(k)
                else:
                    values.append({"value": entry["value"], "source": entry.get("source"), "from_models": [k]})
            fields.append({"id": f["id"], "name": f["name"], "values": values,
                           "same_for_all": len(values) == 1 and len(values[0]["from_models"]) == len(members)})
        out["domains"].append({"domain": d, "title": spec["title"], "fields": fields})
    return out


def lookup_card(version_key=None, family=None, developer=None, domains=DOMAINS, known=None):
    """The most specific card available. `known` limits the cards to these model keys (e.g. leave out a model
    hidden in a test, so the card can't come from the model the identifier has never seen)."""
    if version_key and (known is None or version_key in known) and load_card(domains[0], version_key) is not None:
        card = build_card(version_key, domains=domains)
        return {"level": "version", "label": MODELS.get(version_key, (None, version_key))[1],
                "known_models": [version_key], **card}
    why = ""
    if family and family != "Unknown":
        members = _members(lambda k: MODELS[k][0] == family, known)
        if len(members) >= MIN_FAMILY_MODELS:
            return _group_card("family", family, members, domains)
        if members:
            why = (f" (identified as {family}, but only one {family} version is known and it didn't fit, "
                   f"so the line isn't certain)")
        developer = developer or DEVELOPER.get(family)
    if developer and developer != "Unknown":
        members = _members(lambda k: DEVELOPER[MODELS[k][0]] == developer, known)
        if members:
            return _group_card("developer", developer, members, domains, why)
    return {"level": "none", "label": None, "model_key": None, "confirmed": False, "known_models": [],
            "note": "No developer, family or version identified, so no card can be attached.", "domains": []}