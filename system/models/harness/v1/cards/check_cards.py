"""Check every card file and show which models and domains are complete.

    python check_cards.py            # check everything, print a coverage table
    python check_cards.py --todo     # also list each field still marked TODO

Run it before committing. It exits with an error if a file is broken, so mistakes are caught early.
"""
import argparse
import sys

from cardlib import (DATA_DIR, DOMAINS, HEADER_KEYS, card_models, collector_models, is_todo, licences,
                     load_fields, load_yaml)

EVIDENCE = set(load_fields("risk")["evidence_levels"])


def check_file(domain, path, models, lics):
    """Returns (errors, todos) for one card file."""
    errors, todos = [], []
    try:
        card = load_yaml(path)
    except Exception as e:                       # broken YAML
        return [f"{path.name}: cannot be read ({e})"], []

    for key in HEADER_KEYS:
        if is_todo(card.get(key)):
            todos.append(f"header '{key}'") if card.get(key) is not None else errors.append(f"missing header '{key}'")
    if card.get("domain") != domain:
        errors.append(f"domain is '{card.get('domain')}' but the file is in data/{domain}/")
    if card.get("model_key") != path.stem:
        errors.append(f"model_key '{card.get('model_key')}' does not match the file name")
    if models and path.stem not in models:
        errors.append(f"'{path.stem}' is not in collector/models.yaml")
    if card.get("access") not in ("open", "closed", None) and not is_todo(card.get("access")):
        errors.append("access must be 'open' or 'closed'")

    spec = {f["id"]: f for f in load_fields(domain)["fields"]}
    stored = card.get("fields") or {}
    for fid, f in spec.items():
        if f["filled_by"] != "research":
            if fid in stored:
                errors.append(f"'{fid}' is {f['filled_by']}-filled and should not be in the file")
            continue
        entry = stored.get(fid)
        if not isinstance(entry, dict):
            errors.append(f"missing field '{fid}'")
            continue
        if is_todo(entry.get("value")):
            todos.append(fid)
        elif is_todo(entry.get("source")):
            errors.append(f"'{fid}' has a value but no source")
        if domain == "risk" and not is_todo(entry.get("evidence")) and entry.get("evidence") not in EVIDENCE:
            errors.append(f"'{fid}' evidence must be one of {sorted(EVIDENCE)}")
        if domain == "risk" and is_todo(entry.get("evidence")) and not is_todo(entry.get("value")):
            errors.append(f"'{fid}' needs an evidence level")
    for fid in stored:
        if fid not in spec:
            errors.append(f"unknown field '{fid}' (check the spelling in fields/{domain}.yaml)")

    if domain == "compliance":
        lid = card.get("licence_id")
        if is_todo(lid):
            todos.append("licence_id")
        elif lid not in lics:
            errors.append(f"licence_id '{lid}' is not in collector/licences.yaml")
        elif path.stem not in (lics[lid].get("applies_to") or []):
            errors.append(f"add '{path.stem}' to applies_to of '{lid}' in collector/licences.yaml")
    return errors, todos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--todo", action="store_true", help="list fields still marked TODO")
    args = ap.parse_args()

    models, lics = collector_models(), licences()
    keys = sorted(set(card_models()) | set(models))
    table, all_errors, families = {}, 0, {}
    for k in keys:
        for d in DOMAINS:
            path = DATA_DIR / d / f"{k}.yaml"
            if not path.exists():
                table[k, d] = "missing"
                continue
            errors, todos = check_file(d, path, models, lics)
            families.setdefault(k, set()).add(load_yaml(path).get("family"))
            for e in errors:
                print(f"ERROR  data/{d}/{k}.yaml: {e}")
            all_errors += len(errors)
            if args.todo and todos:
                print(f"TODO   data/{d}/{k}.yaml: {', '.join(todos)}")
            table[k, d] = "ERROR" if errors else (f"{len(todos)} TODO" if todos else "done")
    for k, fams in families.items():
        if len(fams) > 1:
            print(f"ERROR  {k}: family differs between its cards ({', '.join(map(str, fams))})")
            all_errors += 1

    width = max(len(k) for k in keys) + 2
    print("\n" + "model".ljust(width) + "".join(d.ljust(13) for d in DOMAINS))
    for k in keys:
        print(k.ljust(width) + "".join(table[k, d].ljust(13) for d in DOMAINS))
    print(f"\n{all_errors} error(s).")
    sys.exit(1 if all_errors else 0)


if __name__ == "__main__":
    main()
