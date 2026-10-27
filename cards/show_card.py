"""Print a model's domain cards, or the family-level fields when only the family is known.

    python show_card.py llama3.1-8b                     # all four cards
    python show_card.py llama3.1-8b --domain risk       # one card
    python show_card.py --family Llama                  # version unknown: family-level fields only
    python show_card.py gemma3-4b --json > card.json    # for the website / identifier
"""
import argparse
import json
import textwrap

from cardlib import DOMAINS, build_card

LABEL = {"organization": "entered by the bank", "system": "filled by our system",
         "licence_library": "from collector/licences.yaml"}


def fmt(value, indent="      "):
    if isinstance(value, (dict, list)):
        text = yaml_dump(value)
    else:
        text = str(value)
    return "\n".join(textwrap.fill(line, 100, initial_indent=indent, subsequent_indent=indent) or indent
                     for line in text.splitlines())


def yaml_dump(value):
    import yaml
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=1000).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model_key", nargs="?")
    ap.add_argument("--family", help="show family-level fields only (version unknown)")
    ap.add_argument("--domain", choices=DOMAINS, action="append", help="only this card (repeatable)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args()
    if not args.model_key and not args.family:
        ap.error("give a model_key or --family")

    card = build_card(args.model_key, args.family, args.domain or DOMAINS)
    if args.json:
        print(json.dumps(card, indent=2, ensure_ascii=False, default=str))
        return

    if card["confirmed"]:
        print(f"\n{card['name']}  ({card['model_key']}, {card['family']} family, {card['access']} model)")
    else:
        print(f"\n{card['family']} family, version unknown. Known models: {', '.join(card['known_models'])}")
        print(textwrap.fill(card["note"], 100))
    for dom in card["domains"]:
        print(f"\n=== {dom['title']} ===" + (f"  (retrieved {dom['retrieved_at']})" if dom.get("retrieved_at") not in (None, "None") else ""))
        for f in dom["fields"]:
            if card["confirmed"]:
                tag = f" [{LABEL[f['filled_by']]}]" if f["filled_by"] in LABEL else ""
                extra = f" (evidence: {f['evidence']})" if f.get("evidence") else ""
                print(f"  {f['name']}{tag}{extra}")
                print(fmt(f["value"]))
                if f.get("source"):
                    print(fmt(f"Source: {', '.join(f['source']) if isinstance(f['source'], list) else f['source']}"))
            else:
                print(f"  {f['name']}")
                for v in f["values"] or [{"from_model": "-", "value": "No data for this family"}]:
                    print(fmt(f"[{v['from_model']}] {v['value'] if not isinstance(v['value'], (dict, list)) else yaml_dump(v['value'])}"))


if __name__ == "__main__":
    main()
