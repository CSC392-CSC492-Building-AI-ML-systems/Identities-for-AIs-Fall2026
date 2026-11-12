"""Shared helpers for the domain cards: loading field definitions, card data and the collector files.

Other code (the identifier, the website backend) can import build_card() to get a card as a dict:
    from cards.cardlib import build_card
    card = build_card("llama3.1-8b")            # exact model identified
    card = build_card(family="Llama")           # only the family identified ("Unknown" version)
"""
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
FIELDS_DIR = HERE / "fields"
DATA_DIR = HERE / "data"
COLLECTOR = HERE.parent / "collector"
DOMAINS = ["compliance", "governance", "evaluation", "risk"]
HEADER_KEYS = ["model_key", "name", "family", "access", "domain", "retrieved_at"]
NOT_STORED = {"organization", "system", "licence_library"}   # filled_by values that have no data in data/


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_fields(domain):
    """Field definitions for one domain, in display order."""
    return load_yaml(FIELDS_DIR / f"{domain}.yaml")


def research_fields(domain):
    return [f for f in load_fields(domain)["fields"] if f["filled_by"] == "research"]


def card_path(domain, model_key):
    return DATA_DIR / domain / f"{model_key}.yaml"


def load_card(domain, model_key):
    path = card_path(domain, model_key)
    return load_yaml(path) if path.exists() else None


def collector_models():
    """model_key -> entry from collector/models.yaml (mock-model left out)."""
    path = COLLECTOR / "models.yaml"
    if not path.exists():
        return {}
    return {m["model_key"]: m for m in load_yaml(path)["models"] if m.get("provider") != "mock"}


def licences():
    path = COLLECTOR / "licences.yaml"
    return {l["licence_id"]: l for l in load_yaml(path)["licences"]} if path.exists() else {}


def card_models():
    """Every model_key that has at least one card file."""
    return sorted({p.stem for d in DOMAINS for p in (DATA_DIR / d).glob("*.yaml")})


def is_todo(value):
    return value is None or value == "" or (isinstance(value, str) and value.strip().upper().startswith("TODO"))


def _licence_conditions(compliance_card):
    lic = licences().get((compliance_card or {}).get("licence_id"))
    if not lic:
        return None
    return {"value": {"conditions": lic.get("conditions", []), "restrictions": lic.get("restrictions", []),
                      "bank_note": lic.get("bank_note")},
            "source": lic.get("usage_policy_url") or lic.get("official_url"),
            "retrieved_at": str(lic.get("retrieved_at"))}


def _domain_card(domain, model_key):
    """One domain of one model: every field in order, with its value or the placeholder."""
    spec, data = load_fields(domain), load_card(domain, model_key)
    stored = (data or {}).get("fields", {})
    out = []
    for f in spec["fields"]:
        entry = {"id": f["id"], "name": f["name"], "filled_by": f["filled_by"], "level": f["level"]}
        if f["filled_by"] == "research":
            entry.update(stored.get(f["id"]) or {"value": f["if_missing"], "source": None, "missing": True})
        elif f["filled_by"] == "licence_library":
            entry.update(_licence_conditions(data) or {"value": f["if_missing"], "source": None, "missing": True})
        else:
            entry.update({"value": f["if_missing"].replace('"', ""), "source": None, "placeholder": True})
        out.append(entry)
    return {"domain": domain, "title": spec["title"], "retrieved_at": str((data or {}).get("retrieved_at")),
            "fields": out}


def build_card(model_key=None, family=None, domains=DOMAINS):
    """Card for an exact model, or (family=...) the family-level fields of the known models in that family."""
    if model_key:
        header = next((load_card(d, model_key) for d in DOMAINS if load_card(d, model_key)), None)
        if header is None:
            raise KeyError(f"No cards for model '{model_key}'")
        return {"model_key": model_key, "name": header.get("name"), "family": header.get("family"),
                "access": header.get("access"), "confirmed": True,
                "domains": [_domain_card(d, model_key) for d in domains]}

    members = [k for k in card_models()
               if any((load_card(d, k) or {}).get("family", "").lower() == family.lower() for d in DOMAINS)]
    if not members:
        raise KeyError(f"No cards for family '{family}'")
    result = {"model_key": None, "family": family, "confirmed": False, "known_models": members,
              "note": "Version unknown. Showing family-level fields from the known models in this family: "
                      "possible obligations, not confirmed for the deployed model.", "domains": []}
    for d in domains:
        fields = []
        for f in load_fields(d)["fields"]:
            if f["level"] != "family" or f["filled_by"] in ("organization", "system"):
                continue
            values = []
            for k in members:
                entry = next(e for e in _domain_card(d, k)["fields"] if e["id"] == f["id"])
                if not entry.get("missing") and entry["value"] not in [v["value"] for v in values]:
                    values.append({"from_model": k, "value": entry["value"], "source": entry.get("source")})
            fields.append({"id": f["id"], "name": f["name"], "values": values})
        result["domains"].append({"domain": d, "title": load_fields(d)["title"], "fields": fields})
    return result
