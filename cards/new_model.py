"""Create blank card files for a new model, with a "where to look" hint above every field.

    python new_model.py mistral-small-3.2 --name "Mistral Small 3.2" --family Mistral --access open --by Tiana
    python new_model.py mistral-small-3.2 ... --domain risk      # only the risk card

Existing files are never overwritten. Fill in each TODO, then run: python check_cards.py
"""
import argparse
import datetime

from cardlib import DOMAINS, card_path, collector_models, research_fields


def blank_card(domain, args):
    lines = [f"model_key: {args.model_key}", f'name: "{args.name}"', f"family: {args.family}",
             f"access: {args.access}", f"domain: {domain}", f"retrieved_at: {datetime.date.today()}",
             f"researched_by: {args.by}"]
    if domain == "compliance":
        lines.append("licence_id: TODO   # an entry in collector/licences.yaml (add one if the licence is new)")
    lines.append("fields:")
    for f in research_fields(domain):
        where = f["where_open"] if args.access == "open" else f["where_closed"]
        lines.append(f"  # {f['name']}. Look in: {where}. If not found: {f['if_missing']}")
        lines.append(f"  {f['id']}:")
        if domain == "risk":
            lines.append("    evidence: TODO   # high | moderate | low | none")
        lines.append("    value: TODO")
        lines.append("    source: TODO")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model_key", help="same model_key as in collector/models.yaml")
    ap.add_argument("--name", required=True, help='display name, e.g. "Llama 3.1 8B Instruct"')
    ap.add_argument("--family", required=True, help="e.g. Llama, Qwen, Gemma, Gemini, Claude, GPT")
    ap.add_argument("--access", required=True, choices=["open", "closed"])
    ap.add_argument("--by", default="TODO", help="your name")
    ap.add_argument("--domain", choices=DOMAINS, action="append", help="only this card (repeatable)")
    args = ap.parse_args()

    if args.model_key not in collector_models():
        print(f"Note: '{args.model_key}' is not in collector/models.yaml yet. Add it there too.")
    for domain in args.domain or DOMAINS:
        path = card_path(domain, args.model_key)
        if path.exists():
            print(f"skipped (already exists): {path}")
            continue
        path.write_text(blank_card(domain, args), encoding="utf-8")
        print(f"created: {path}")


if __name__ == "__main__":
    main()
