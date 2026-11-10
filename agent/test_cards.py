"""Test the domain cards that the identifier attaches, and make an HTML report.

The identifier should attach the most specific card it can: the exact version's card, else the family's
(product line) shared fields, else the developer's shared fields, else none. This script checks that:

  1. Lookup tests: every model, family and developer gets the right card, hidden models are never used,
     and family / developer cards only show fields that hold for the whole group.
  2. Results tests: for every chatbot in a results file, is the attached card for the right model / family /
     developer, and is it as specific as it could be given which models were known?

    python test_cards.py results/results_probes6_all-models.jsonl results/results_probes6_hide-luna.jsonl
    python test_cards.py --no-report results/results_probes6_all-models.jsonl     # terminal only

Writes results/cards_report.html (open it in a browser) and results/cards_test.json.
"""
import argparse, datetime, html, json, sys
from collections import Counter
from pathlib import Path

from card_lookup import LEVELS, MIN_FAMILY_MODELS, lookup_card
from identify import DEVELOPER, HERE, MODELS
from cardlib import DOMAINS, card_models, load_fields

NAME_TO_KEY = {v[1]: k for k, v in MODELS.items()}


def fam(k): return MODELS[k][0]
def dev(k): return DEVELOPER[MODELS[k][0]]


# ---------------------------------------------------------------- 1. lookup tests
def lookup_tests():
    tests = []
    def check(name, ok, detail=""):
        tests.append({"test": name, "ok": bool(ok), "detail": detail})

    keys = [k for k in card_models() if k in MODELS]
    check("every model in identify.MODELS has cards", set(keys) == set(MODELS),
          ", ".join(sorted(set(MODELS) - set(keys))) or f"all {len(MODELS)}")
    group_ids = {d: {f["id"] for f in load_fields(d)["fields"]
                     if f["level"] == "family" and f["filled_by"] not in ("organization", "system")} for d in DOMAINS}
    for k in keys:
        c = lookup_card(version_key=k, family=fam(k), developer=dev(k))
        check(f"{k}: exact version card", c["level"] == "version" and c["model_key"] == k
              and len(c["domains"]) == 4, f"level {c['level']}")
    for f in sorted({fam(k) for k in keys}):
        c = lookup_card(family=f)
        want = sorted(k for k in keys if fam(k) == f)
        if len(want) < MIN_FAMILY_MODELS:      # one known version: the developer card instead
            want_dev = sorted(k for k in keys if dev(k) == DEVELOPER[f])
            check(f"family {f} (1 known version): developer card from {', '.join(want_dev)}",
                  c["level"] == "developer" and c["known_models"] == want_dev)
            continue
        check(f"family {f}: card from {', '.join(want)}", c["level"] == "family" and c["known_models"] == want)
        extra = [x["id"] for d in c["domains"] for x in d["fields"] if x["id"] not in group_ids[d["domain"]]]
        check(f"family {f}: only family-level fields", not extra, ", ".join(extra))
    for d_ in sorted({dev(k) for k in keys}):
        c = lookup_card(developer=d_)
        want = sorted(k for k in keys if dev(k) == d_)
        check(f"developer {d_}: card from {', '.join(want)}", c["level"] == "developer" and c["known_models"] == want)
    # hidden models: the card must never come from the hidden model
    for k in keys:
        known = [x for x in keys if x != k]
        c = lookup_card(version_key=k, family=fam(k), developer=dev(k), known=known)
        siblings = [x for x in known if fam(x) == fam(k)]
        want = "family" if len(siblings) >= MIN_FAMILY_MODELS else (
            "developer" if any(dev(x) == dev(k) for x in known) else "none")
        check(f"{k} hidden: falls back to {want}", c["level"] == want and k not in c["known_models"],
              f"got {c['level']} from {', '.join(c['known_models']) or '-'}")
    c = lookup_card(family="Unknown", developer="Unknown")
    check("nothing identified: no card", c["level"] == "none")
    c = lookup_card(family="Mistral", developer="Mistral AI")
    check("unknown family and developer: no card", c["level"] == "none")
    return tests


# ---------------------------------------------------------------- 2. results tests
def best_level(true_key, known):
    if true_key in known:
        return "version"
    if sum(fam(k) == fam(true_key) for k in known) >= MIN_FAMILY_MODELS:
        return "family"
    if any(dev(k) == dev(true_key) for k in known):
        return "developer"
    return "none"


def grade(row):
    true_key = row["session"].split("|")[0]
    known = [k for k in MODELS if k != row.get("left_out")]
    pred_key = NAME_TO_KEY.get(row.get("pred_version"))
    card = lookup_card(version_key=pred_key, family=row.get("pred_family"), developer=row.get("pred_developer"),
                       known=known)
    lvl = card["level"]
    right = {"version": card.get("model_key") == true_key, "family": card["label"] == fam(true_key),
             "developer": card["label"] == dev(true_key), "none": None}[lvl]
    best = best_level(true_key, known)
    if lvl == "none":
        outcome = "no card"
    elif not right:
        outcome = "wrong card"
    elif LEVELS.index(lvl) == LEVELS.index(best):
        outcome = "right, most specific"
    else:
        outcome = "right, less specific"
    return {"session": row["session"], "true_model": MODELS[true_key][1], "persona": row.get("persona_id"),
            "hidden": row.get("left_out"), "identified": {"developer": row.get("pred_developer"),
            "family": row.get("pred_family"), "version": row.get("pred_version")},
            "card_level": lvl, "card_label": card["label"], "best_level": best, "outcome": outcome,
            "card_id": f"{lvl}:{card['label']}:{','.join(card['known_models'])}", "card": card}


def run_tests(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    graded = [grade(r) for r in rows]
    return {"file": str(path), "hidden": rows[0].get("left_out") if rows else None, "chatbots": graded,
            "outcomes": Counter(g["outcome"] for g in graded),
            "by_level": {l: Counter(g["outcome"] for g in graded if g["card_level"] == l) for l in LEVELS}}


# ---------------------------------------------------------------- 3. report
CSS = """
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e3e2dd;--accent:#2f5d8a;
--ok:#2e7d4f;--okbg:#e6f2ea;--warn:#8a6a10;--warnbg:#f6efd9;--bad:#b23b2e;--badbg:#f7e3e0;--none:#6b6b66;--nonebg:#ecebe7}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;--muted:#a3a29b;--line:#34332f;
--accent:#8db4dc;--ok:#7cc79a;--okbg:#1f3328;--warn:#e0c060;--warnbg:#3a321a;--bad:#f08a7c;--badbg:#3d2420;--none:#a3a29b;--nonebg:#2a2a27}}
:root[data-theme="dark"]{--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;--muted:#a3a29b;--line:#34332f;
--accent:#8db4dc;--ok:#7cc79a;--okbg:#1f3328;--warn:#e0c060;--warnbg:#3a321a;--bad:#f08a7c;--badbg:#3d2420;--none:#a3a29b;--nonebg:#2a2a27}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 16px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 10px}
h3{font-size:16px;margin:18px 0 8px}.muted{color:var(--muted)}a{color:var(--accent)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:14px 0}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}.tile .n{font-size:28px;font-weight:650}
.tile .l{color:var(--muted);font-size:13px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:4px 14px 14px;margin:10px 0}
.ladder{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}.step{border:1px solid var(--line);background:var(--panel);border-radius:8px;padding:8px 12px}
.step b{display:block}.arrow{color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:13px}.scroll{overflow-x:auto}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12.5px;white-space:nowrap}
.ok{background:var(--okbg);color:var(--ok)}.warn{background:var(--warnbg);color:var(--warn)}.bad{background:var(--badbg);color:var(--bad)}.none{background:var(--nonebg);color:var(--none)}
.lvl{font-size:12px;border:1px solid var(--line);border-radius:6px;padding:0 6px;color:var(--muted)}
details{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin:8px 0}summary{cursor:pointer;padding:10px 14px;font-weight:600}
details .body{padding:0 14px 14px}.note{background:var(--warnbg);color:var(--ink);border-radius:8px;padding:8px 12px;font-size:14px}
.field td:first-child{width:26%;font-weight:600}.src{font-size:12.5px;color:var(--muted);word-break:break-all}.from{font-size:12.5px;color:var(--muted)}
ul{margin:4px 0;padding-left:20px}.pass{color:var(--ok)}.fail{color:var(--bad)}
.filter{margin:6px 0 10px;display:flex;gap:6px;flex-wrap:wrap}.filter button{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:999px;padding:3px 10px;cursor:pointer;font:inherit;font-size:13px}
.filter button.on{background:var(--accent);color:var(--panel);border-color:var(--accent)}
"""
CHIP = {"right, most specific": "ok", "right, less specific": "warn", "wrong card": "bad", "no card": "none"}
E = html.escape


def render_value(v):
    if isinstance(v, dict):
        return "".join(f"<div><b>{E(str(k).replace('_', ' ').capitalize())}:</b> {render_value(x)}</div>"
                       for k, x in v.items() if x not in (None, [], ""))
    if isinstance(v, list):
        return "<ul>" + "".join(f"<li>{render_value(x)}</li>" for x in v) + "</ul>"
    return E(str(v))


def render_source(s):
    if not s:
        return ""
    items = s if isinstance(s, list) else [s]
    links = [f'<a href="{E(x)}">{E(x)}</a>' if str(x).startswith("http") else E(str(x)) for x in items]
    return '<div class="src">Source: ' + " · ".join(links) + "</div>"


def render_card(card, anchor):
    lvl, label = card["level"], card["label"]
    head = {"version": f"{label} — exact version", "family": f"{label} family — shared fields",
            "developer": f"{label} (developer) — shared fields"}[lvl]
    out = [f'<details id="{anchor}"><summary>{E(head)} <span class="lvl">{lvl}</span></summary><div class="body">']
    if lvl != "version":
        out.append(f'<p class="note">{E(card["note"])} From: {E(", ".join(MODELS[k][1] for k in card["known_models"]))}.</p>')
    for d in card["domains"]:
        out.append(f"<h3>{E(d['title'])}</h3><div class='scroll'><table>")
        for f in d["fields"]:
            if lvl == "version":
                tag = " <span class='lvl'>filled by the bank</span>" if f.get("placeholder") else (
                      " <span class='lvl'>not found</span>" if f.get("missing") else "")
                out.append(f"<tr class='field'><td>{E(f['name'])}{tag}</td><td>{render_value(f.get('value'))}"
                           f"{render_source(f.get('source'))}</td></tr>")
            else:
                if not f["values"]:
                    cell = "<span class='muted'>No value found for these models</span>"
                elif f["same_for_all"]:
                    only = card["known_models"][0]
                    tail = ("Same for all models in this group" if len(card["known_models"]) > 1 else
                            f"From {MODELS[only][1]}, the only known model in this group")
                    cell = render_value(f["values"][0]["value"]) + render_source(f["values"][0]["source"]) + \
                           f"<div class='from'>{E(tail)}</div>"
                else:
                    cell = "".join(f"<div style='margin-bottom:8px'>{render_value(v['value'])}<div class='from'>"
                                   f"{E(', '.join(MODELS[k][1] for k in v['from_models']))}</div>"
                                   f"{render_source(v['source'])}</div>" for v in f["values"])
                out.append(f"<tr class='field'><td>{E(f['name'])}</td><td>{cell}</td></tr>")
        out.append("</table></div>")
    out.append("</div></details>")
    return "".join(out)


def report_body(lookup, runs):
    """The report's content (no <html>/<head>), so it can also be published as a page."""
    cards, anchors = {}, {}
    for r in runs:
        for g in r["chatbots"]:
            if g["card_level"] != "none" and g["card_id"] not in anchors:
                anchors[g["card_id"]] = f"card{len(anchors) + 1}"
                cards[g["card_id"]] = g["card"]
    passed = sum(t["ok"] for t in lookup)
    body = [f"<main><h1>Domain card test</h1><p class='muted'>Which card the agentic identifier attaches to each chatbot, "
            f"and whether it is the right one. Made {datetime.date.today().isoformat()} by <code>test_cards.py</code>.</p>",
            "<h2>How a card is chosen</h2><div class='ladder'>"
            "<div class='step'><b>1. Exact version</b>full card (all 4 domains)</div><span class='arrow'>→ if version Unknown</span>"
            "<div class='step'><b>2. Family</b>fields shared by the line's known models (needs 2+ known versions)</div>"
            "<span class='arrow'>→ if family Unknown</span>"
            "<div class='step'><b>3. Developer</b>fields shared by the company's models</div><span class='arrow'>→ if nothing</span>"
            "<div class='step'><b>4. No card</b>sent for review</div></div>"
            "<p class='muted'>A card is <b>right</b> when the chatbot's real model belongs to it (same version, family or developer), "
            "and <b>most specific</b> when no more specific card was possible with the models the identifier knew. "
            "Hidden models are never used for cards.</p>"]
    for r in runs:
        n, o = len(r["chatbots"]), r["outcomes"]
        title = Path(r["file"]).name + (f" — {MODELS[r['hidden']][1]} hidden" if r["hidden"] else " — all models known")
        rid = Path(r["file"]).stem
        right = o["right, most specific"] + o["right, less specific"]
        body.append(f"<h2>{E(title)}</h2><div class='tiles'>"
                    f"<div class='tile'><div class='n'>{right}/{n}</div><div class='l'>right card ({100 * right // n}%)</div></div>"
                    f"<div class='tile'><div class='n'>{o['right, most specific']}/{n}</div><div class='l'>right and most specific</div></div>"
                    f"<div class='tile'><div class='n'>{o['wrong card']}</div><div class='l'>wrong card (for another model)</div></div>"
                    f"<div class='tile'><div class='n'>{o['no card']}</div><div class='l'>no card</div></div></div>")
        body.append("<div class='panel scroll'><table><tr><th>Card level</th><th>Chatbots</th><th>Right, most specific</th>"
                    "<th>Right, less specific</th><th>Wrong card</th></tr>")
        for l in LEVELS:
            c = r["by_level"][l]
            if sum(c.values()):
                body.append(f"<tr><td>{l}</td><td>{sum(c.values())}</td><td>{c['right, most specific']}</td>"
                            f"<td>{c['right, less specific']}</td><td>{c['wrong card']}</td></tr>")
        body.append("</table></div>")
        body.append(f"<div class='filter' data-run='{rid}'>" + "".join(
            f"<button data-f='{k}' class='{'on' if k == 'all' else ''}'>{lab}</button>" for k, lab in
            [("all", "All"), ("right, most specific", "Most specific"), ("right, less specific", "Less specific"),
             ("wrong card", "Wrong"), ("no card", "No card")]) + "</div>")
        body.append(f"<details><summary>All {n} chatbots</summary><div class='body scroll'><table id='t-{rid}'>"
                    "<tr><th>Real model</th><th>Persona</th><th>Identified as</th><th>Card attached</th><th>Result</th></tr>")
        for g in r["chatbots"]:
            i = g["identified"]
            ident = " / ".join(str(i[x] or "Unknown") for x in ("developer", "family", "version"))
            link = (f"<a href='#{anchors[g['card_id']]}'>{E(g['card_label'])}</a> <span class='lvl'>{g['card_level']}</span>"
                    if g["card_level"] != "none" else "<span class='muted'>none</span>")
            body.append(f"<tr data-o='{E(g['outcome'])}'><td>{E(g['true_model'])}</td><td>{E(g['persona'] or '')}</td>"
                        f"<td>{E(ident)}</td><td>{link}</td><td><span class='chip {CHIP[g['outcome']]}'>{E(g['outcome'])}</span></td></tr>")
        body.append("</table></div></details>")
    body.append(f"<h2>Lookup tests: {passed}/{len(lookup)} passed</h2><details><summary>Show all tests</summary>"
                "<div class='body scroll'><table><tr><th>Test</th><th>Result</th><th>Detail</th></tr>")
    for t in lookup:
        body.append(f"<tr><td>{E(t['test'])}</td><td class='{'pass' if t['ok'] else 'fail'}'>{'pass' if t['ok'] else 'FAIL'}</td>"
                    f"<td class='muted'>{E(t['detail'])}</td></tr>")
    body.append("</table></div></details>")
    body.append(f"<h2>Cards attached ({len(cards)})</h2><p class='muted'>Each card the tests attached, once. "
                "Click a card name in the chatbot table to jump here.</p>")
    order = sorted(cards, key=lambda c: (LEVELS.index(cards[c]["level"]), cards[c]["label"]))
    body += [render_card(cards[c], anchors[c]) for c in order]
    body.append("</main>")
    js = """<script>
document.querySelectorAll('.filter').forEach(f=>f.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
f.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));const t=document.getElementById('t-'+f.dataset.run);
t.closest('details').open=true;t.querySelectorAll('tr[data-o]').forEach(r=>r.style.display=(b.dataset.f==='all'||r.dataset.o===b.dataset.f)?'':'none');}));
document.querySelectorAll('a[href^="#card"]').forEach(a=>a.addEventListener('click',()=>{const d=document.querySelector(a.getAttribute('href'));if(d)d.open=true;}));
</script>"""
    return f"<style>{CSS}</style>{''.join(body)}{js}"


def write_report(lookup, runs, path):
    page = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Domain Card Test</title></head>"
            f"<body>{report_body(lookup, runs)}</body></html>")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(page, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="+", help="results files from probe_identify.py")
    ap.add_argument("--report", default=str(HERE / "results" / "cards_report.html"))
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args()

    lookup = lookup_tests()
    passed = sum(t["ok"] for t in lookup)
    print(f"Lookup tests: {passed}/{len(lookup)} passed")
    for t in lookup:
        if not t["ok"]:
            print(f"  FAIL {t['test']} ({t['detail']})")
    runs = []
    for p in args.results:
        r = run_tests(p)
        if r["chatbots"]:
            runs.append(r)
        else:
            print(f"(skipped {Path(p).name}: no results in it yet)")
    for r in runs:
        n, o = len(r["chatbots"]), r["outcomes"]
        print(f"\n{Path(r['file']).name}" + (f" (hidden: {r['hidden']})" if r["hidden"] else ""))
        print(f"  right card: {o['right, most specific'] + o['right, less specific']}/{n} "
              f"(most specific {o['right, most specific']}, less specific {o['right, less specific']}) | "
              f"wrong card: {o['wrong card']} | no card: {o['no card']}")
        for l in LEVELS:
            c = r["by_level"][l]
            if sum(c.values()):
                print(f"  {l:9} {sum(c.values()):3} chatbots: " + ", ".join(f"{k} {v}" for k, v in c.items()))
        for g in r["chatbots"]:
            if g["outcome"] == "wrong card":
                print(f"    wrong: {g['true_model']} {g['persona']} got the {g['card_label']} {g['card_level']} card")
    out = Path(args.report).with_name("cards_test.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"lookup_tests": lookup, "runs": [{**{k: v for k, v in r.items() if k != "chatbots"},
               "chatbots": [{k: v for k, v in g.items() if k != "card"} for g in r["chatbots"]]} for r in runs]},
              open(out, "w", encoding="utf-8"), indent=1, default=dict)
    if not args.no_report:
        write_report(lookup, runs, args.report)
        print(f"\nReport -> {args.report}")
    print(f"Details -> {out}")
    sys.exit(0 if passed == len(lookup) else 1)


if __name__ == "__main__":
    main()