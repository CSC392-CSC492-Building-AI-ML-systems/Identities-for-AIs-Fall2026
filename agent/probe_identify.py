"""
Probe-based identifier (Stage 2): judge a whole chatbot from its answers to a fixed set of probes.

In a real deployment we can send the chatbot our own questions. So instead of guessing from one answer,
this sends the same probes to every chatbot and judges all its answers together. For each probe the
judge sees how each known model answers it (an automatic profile plus one example) and the chatbot's
answer. A name detector (a "tool") adds hard evidence: the makers the chatbot names.

One test case = one chatbot = one model under one persona, using its sample_index 2 answers.
Profiles and examples come only from sample_index 0 and 1, so the judge never sees the tested answers.
With --ref-persona other (default), the test persona is also left out of the references, because we
don't know a real deployment's system prompt.

    python probe_identify.py --dry-run                         # show what the judge would see
    python probe_identify.py --provider mock                   # test the pipeline
    python probe_identify.py                                   # all chatbots (5 models x 8 personas)
    python probe_identify.py --leave-out qwen3.5-9b            # should answer "Unknown" for the hidden model
    python probe_identify.py --leave-out gemma3-4b             # hidden family: should be Unknown family
    python probe_identify.py --probes LM-01,LM-05,I1,I2        # try a different probe set
    python probe_identify.py --domain compliance               # attach the compliance card to each result
    python probe_identify.py --check baseline                  # monitoring: compare with the deployment's own baseline
    python probe_identify.py --check baseline --rescore results/old.jsonl --out results/new.jsonl
                                                               # re-apply the code checks to saved judge answers (free)

After the judge picks the closest known version, code checks each probe answer against that model's
reference answers (dates stated, refusals, length). If 3 or more probes don't fit (--max-misfit), the
version becomes "Unknown"; if the chatbot names a maker we don't know, the family does too. The fit score
(share of probes that fit) is the confidence to use, because the judge's own stays high even when wrong.
"""
import argparse, json, re, statistics, time
from collections import Counter, defaultdict
from pathlib import Path

from identify import (MODELS, DEVELOPER, HERE, call_llm, expected_answer, licence_lookup, load_env,
                      load_prompt_texts, load_records, parse)

DEFAULT_PROBES = ["LM-01", "LM-05", "LM-06", "I1", "I2", "V1-15"]
EXAMPLE_CHARS = 300          # example answer shown per model and probe
ANSWER_CHARS = 800           # chatbot answer shown per probe

# Name detector: maker / model names -> the company that makes the model (the developer).
NAMES = {
    "Meta":      r"\b(meta|llama|facebook)\b",
    "Alibaba":   r"\b(qwen|alibaba|tongyi)\b",
    "Google":    r"\b(gemma|gemini|google|deepmind)\b",
    "Anthropic": r"\b(claude|anthropic)\b",
    "OpenAI":    r"\b(openai|chatgpt|gpt-?\d)",
}
REFUSAL = r"\b(i can'?t|i cannot|i'm not able|i am not able|i'm unable|i am unable|unable to (help|assist|provide))\b"
DATE = r"\b(?:(january|february|march|april|may|june|july|august|september|october|november|december) )?(20[12]\d)\b"

INSTRUCTIONS = """You identify which AI model is behind a chatbot.
We sent the chatbot a fixed set of probe questions. For each probe you see how each known model usually
answers it (a profile measured from many answers, plus one example) and the chatbot's answer.
The chatbot may run under a system prompt (e.g. a bank assistant persona) that hides its identity.

Decide in this order:
1. Family (the product line, e.g. Llama, Gemma, Gemini Flash). Maker or model names the chatbot gives
   (see NAME EVIDENCE) are strong evidence. Otherwise compare behaviour.
2. Version. Choose the known version of that family that fits best, using the probes where they differ
   (e.g. the cutoff date it states, whether it talks about itself or refuses, refusals, answer length).
   Always pick the closest known version; a separate check decides whether it is really that version.
3. If the answers fit no known family, or name a maker that is not in the list, answer "Unknown" for both.

Known models: {models}.
Reply with JSON only, no other text:
{{"family": "<{families}|Unknown>", "version": "<one of the known versions or Unknown>",
  "family_confidence": <0-1>, "version_confidence": <0-1>, "reason": "<one or two sentences naming the probes that decided it>"}}"""


def detect_names(text):
    t = (text or "").lower()
    return [dev for dev, pat in NAMES.items() if re.search(pat, t)]


def name_evidence(answers):
    """Counts how many of the chatbot's answers name each developer. Returns (text for the judge, developer or None)."""
    counts = Counter(d for a in answers for d in set(detect_names(a)))
    if not counts:
        return "No maker or model names found in the chatbot's answers.", None
    text = "; ".join(f"{d} (or its models) named in {n} of {len(answers)} answers" for d, n in counts.most_common())
    return text, (next(iter(counts)) if len(counts) == 1 else None)


def profile(answers):
    """One line describing how a model answers a probe, measured from its reference answers."""
    if not answers:
        return "no reference answers"
    n = len(answers)
    names = Counter(f for a in answers for f in set(detect_names(a)))
    dates = Counter(" ".join(x for x in m if x).title() for a in answers for m in set(re.findall(DATE, a.lower())))
    refuse = sum(bool(re.search(REFUSAL, a.lower())) for a in answers)
    parts = [f"names maker: {', '.join(f'{f} {100 * c // n}%' for f, c in names.most_common(2)) or 'never'}"]
    if dates:
        parts.append("dates stated: " + ", ".join(f"{d} {100 * c // n}%" for d, c in dates.most_common(2)))
    parts.append(f"refuses {100 * refuse // n}%")
    parts.append(f"median length {int(statistics.median(len(a) for a in answers))} chars")
    return " | ".join(parts) + f" (from {n} answers)"


def code_misfits(session, model_refs, rare=0.25, length_factor=3):
    """Probes where the chatbot's answer doesn't fit a model's reference answers, measured in code:
    it states a date the model states in under 25% of its answers, refuses where the model rarely refuses
    (or doesn't refuse where it almost always does), or is over 3x longer or shorter than the model's median."""
    def dates(a):
        return {" ".join(x for x in m if x) for m in re.findall(DATE, a.lower())}
    def refuses(a):
        return bool(re.search(REFUSAL, a.lower()))
    found = []
    for pid, answer in session.items():
        refs = model_refs.get(pid, [])
        if len(refs) < 4:                       # too few reference answers to judge
            continue
        why = []
        if dates(answer) and max(sum(d in dates(r) for r in refs) for d in dates(answer)) / len(refs) < rare:
            why.append("date")
        refuse_share = sum(map(refuses, refs)) / len(refs)
        if (refuses(answer) and refuse_share < rare) or (not refuses(answer) and refuse_share > 1 - rare):
            why.append("refusal")
        median = statistics.median(len(r) for r in refs)
        if len(answer) > length_factor * median or len(answer) < median / length_factor:
            why.append("length")
        if why:
            found.append(f"{pid}: {'/'.join(why)}")
    return found


def baseline_misfits(session, baseline, length_factor=1.5):
    """Probes where the chatbot's answer differs from the deployment's own baseline: earlier answers from the
    approved model under the SAME system prompt. Use this when monitoring a registered deployment.
    A probe doesn't fit when the chatbot states a date the baseline never stated (or none when the baseline
    always did), refuses differently from a baseline that agrees with itself, or is over 1.5x longer or
    shorter than every baseline answer."""
    def dates(a):
        return {" ".join(x for x in m if x) for m in re.findall(DATE, a.lower())}
    def refuses(a):
        return bool(re.search(REFUSAL, a.lower()))
    found = []
    for pid, answer in session.items():
        base = baseline.get(pid, [])
        if len(base) < 2:
            continue
        why = []
        d = dates(answer)
        if (d and not any(x in dates(b) for b in base for x in d)) or (not d and all(dates(b) for b in base)):
            why.append("date")
        if len({refuses(b) for b in base}) == 1 and refuses(answer) != refuses(base[0]):
            why.append("refusal")
        lengths = [len(b) for b in base]
        if len(answer) > length_factor * max(lengths) or len(answer) < min(lengths) / length_factor:
            why.append("length")
        if why:
            found.append(f"{pid}: {'/'.join(why)}")
    return found


IDENTITY_PROBES = ["LM-01", "LM-06", "I1", "I2"]


def self_identifies(text, family):
    """Does the answer say "I am ... <family keyword>" (e.g. "I am Gemini 3.8 Flash")? The keyword is the
    last word of the family name: Flash, Pro, Gemma, Llama, Sonnet... so it works for new models too."""
    kw = re.escape(family.split()[-1].lower())
    return bool(re.search(rf"\bi(?:'m|’m| am)\b(?:(?!\.\s)[^\n]){{0,40}}\b{kw}\b", (text or "").lower()))


def self_id_rate(recs, model_key, persona, family):
    """Share of the model's reference chatbots (other personas, samples 0-1) that call themselves by the family name."""
    groups = defaultdict(bool)
    for r in recs:
        if r["model_key"] == model_key and r["persona_id"] != persona and r["sample_index"] in (0, 1) \
                and r["prompt_id"] in IDENTITY_PROBES:
            groups[(r["persona_id"], r["sample_index"])] |= self_identifies(r["response_text"], family)
    return sum(groups.values()) / len(groups) if groups else 0.0


def apply_rules(pred, names_dev, known, misfits, max_misfit, chatbot_self_id=None, model_self_id_rate=0.0):
    """Rules checked in code, because the judge stays confident even when it is wrong.
    Returns (final prediction, rule that changed the answer)."""
    final, rule = dict(pred), None
    if names_dev and names_dev not in {DEVELOPER[MODELS[k][0]] for k in known}:
        final.update(family="Unknown", version="Unknown")
        rule = f"names {names_dev}, which makes none of the known models"
    elif misfits is not None and len(misfits) >= max_misfit and final.get("version") != "Unknown":
        final["version"] = "Unknown"
        rule = f"{len(misfits)} probes do not fit {pred.get('version')}"
        # A new version of the same line still calls itself by the line's name (e.g. "Gemini 3.9 Flash").
        # If the chosen line's models usually do that and this chatbot doesn't, it is a different line.
        if model_self_id_rate >= 0.75 and chatbot_self_id is False:
            final["family"] = "Unknown"
            rule += f"; never calls itself {pred.get('family')}, which {int(model_self_id_rate * 100)}% of its chatbots do"
    return final, rule


def attach_card(domain, pred_key, family):
    """The domain card for the identified model, or only the family-level fields when the version is Unknown."""
    import sys
    sys.path.insert(0, str(HERE.parent / "cards"))
    from cardlib import build_card
    try:
        if pred_key:
            return build_card(pred_key, domains=[domain])
        if family and family != "Unknown":
            return build_card(family=family, domains=[domain])
    except KeyError:
        pass
    return None


def build_messages(session, refs, known, probes, prompt_text):
    """session: probe_id -> chatbot answer. refs: model_key -> probe_id -> reference answers."""
    parts = []
    for pid in probes:
        if pid not in session:
            continue
        parts.append(f"### PROBE {pid}: {prompt_text.get(pid, '')[:200]}")
        for key in known:
            answers = refs[key].get(pid, [])
            example = answers[0][:EXAMPLE_CHARS].replace("\n", " ") if answers else "(none)"
            parts.append(f"- {MODELS[key][1]}: {profile(answers)}\n  Example: {example}")
        parts.append(f"CHATBOT'S ANSWER:\n{session[pid][:ANSWER_CHARS]}\n")
    evidence, _ = name_evidence(list(session.values()))
    parts.append(f"NAME EVIDENCE (from a name detector run on all the chatbot's answers): {evidence}")
    families = sorted({MODELS[k][0] for k in known})
    system = INSTRUCTIONS.format(models=", ".join(MODELS[k][1] for k in known), families="|".join(families))
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(parts)}]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="google", choices=["google", "anthropic", "openai", "mock"])
    ap.add_argument("--model", default="gemini-3.8-flash")
    ap.add_argument("--probes", default=",".join(DEFAULT_PROBES), help="comma-separated fingerprint prompt IDs")
    ap.add_argument("--ref-persona", default="other", choices=["other", "all"],
                    help="other = leave the test persona out of the references (realistic); all = include it")
    ap.add_argument("--leave-out", choices=list(MODELS), help="hide this model from the judge (tests 'Unknown')")
    ap.add_argument("--min-answers", type=int, default=3, help="skip chatbots with fewer non-empty probe answers")
    ap.add_argument("--check", default="profiles", choices=["profiles", "baseline"],
                    help="profiles = compare with the model's answers under other system prompts (unknown deployment); "
                         "baseline = compare with the deployment's own earlier answers (monitoring a registered deployment)")
    ap.add_argument("--max-misfit", type=int, default=3, help="this many probes not fitting the chosen version -> version Unknown")
    ap.add_argument("--domain", choices=["compliance", "governance", "evaluation", "risk"],
                    help="attach this domain card (from cards/) to each result")
    ap.add_argument("--delay", type=float, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rescore", help="re-apply the code checks to the judge answers saved in this results file "
                                      "(no API calls); use the same --check/--leave-out as that run")
    ap.add_argument("--out")
    args = ap.parse_args()
    probes = args.probes.split(",")
    if not args.out:
        args.out = HERE / "results" / (f"results_probes3_{args.ref_persona}" + ("_baseline" if args.check == "baseline" else "") + (f"_without-{args.leave_out}" if args.leave_out else "")
                           + ("" if probes == DEFAULT_PROBES else f"_{len(probes)}probes") + ".jsonl")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    load_env(HERE.parent / "collector" / ".env")

    recs = [r for r in load_records(MODELS, ["fingerprint"]) if r["prompt_id"] in probes]
    if not recs:
        exit("No fingerprint data found for these probes.")
    prompt_text = {pid: t for (ds, pid), t in load_prompt_texts(["fingerprint"]).items()}
    models = sorted({r["model_key"] for r in recs})
    known = [m for m in models if m != args.leave_out]

    sessions = defaultdict(dict)                 # (model, persona) -> probe -> answer (sample 2)
    for r in recs:
        if r["sample_index"] == 2:
            sessions[(r["model_key"], r["persona_id"])][r["prompt_id"]] = r["response_text"]
    sessions = {k: v for k, v in sessions.items() if len(v) >= args.min_answers}
    print(f"Probes: {', '.join(probes)} | references: {args.ref_persona} personas | check: {args.check} | known: {', '.join(known)}"
          + (f" | hidden: {args.leave_out}" if args.leave_out else "") + f" | testing {len(sessions)} chatbots")

    rescore = {}
    if args.rescore:
        rescore = {r["session"]: r for r in map(json.loads, open(args.rescore, encoding="utf-8"))}
        if Path(args.out) == Path(args.rescore):
            exit("Give --out a new file name when using --rescore.")
    licences = licence_lookup()
    done = {}
    if Path(args.out).exists() and not args.dry_run:
        done = {r["session"]: r for r in map(json.loads, open(args.out, encoding="utf-8"))}
        if done:
            print(f"Continuing: {len(done)} already scored in {args.out}")
    out = None if args.dry_run else open(args.out, "a", encoding="utf-8")
    results = [done[f"{m}|{p}"] for (m, p) in sessions if f"{m}|{p}" in done]

    for i, ((model, persona), session) in enumerate(sorted(sessions.items()), 1):
        sid = f"{model}|{persona}"
        if sid in done:
            continue
        refs = {k: defaultdict(list) for k in known}
        for r in recs:
            if r["model_key"] in refs and r["sample_index"] in (0, 1) and \
                    (args.ref_persona == "all" or r["persona_id"] != persona):
                refs[r["model_key"]][r["prompt_id"]].append(r["response_text"])
        msgs = build_messages(session, refs, known, probes, prompt_text)
        if args.dry_run:
            print(msgs[0]["content"], "\n---\n", msgs[1]["content"])
            print(f"\n(about {len(msgs[0]['content'] + msgs[1]['content']) // 4} tokens)")
            return
        try:
            if args.rescore:                     # reuse the judge's saved answer instead of calling the API
                saved = rescore.get(sid)
                if not saved:
                    continue
                pred = {k: saved.get(f"judge_{k}") for k in ("family", "version")}
                pred.update({k: saved.get(k) for k in ("family_confidence", "version_confidence", "reason")})
            else:
                pred = parse(call_llm(args.provider, args.model, msgs))
        except RuntimeError as e:
            print(f"[{i}/{len(sessions)}] skipped ({e}); run the same command again to retry it")
            continue

        exp_fam, exp_ver = expected_answer(model, known)
        _, names_dev = name_evidence(list(session.values()))
        judge_key = next((k for k in known if MODELS[k][1] == pred.get("version")), None)
        if not judge_key:
            misfits = None
        elif args.check == "baseline":    # the approved model's earlier answers under this same system prompt
            baseline = defaultdict(list)
            for r in recs:
                if r["model_key"] == judge_key and r["persona_id"] == persona and r["sample_index"] in (0, 1):
                    baseline[r["prompt_id"]].append(r["response_text"])
            misfits = baseline_misfits(session, baseline)
        else:
            misfits = code_misfits(session, refs[judge_key])
        fit = round(1 - len(misfits) / len(session), 2) if misfits is not None else None
        fam = pred.get("family") or "Unknown"
        chatbot_self_id = any(self_identifies(session.get(p), fam) for p in IDENTITY_PROBES) if judge_key else None
        rate = self_id_rate(recs, judge_key, persona, fam) if judge_key else 0.0
        final, rule = apply_rules(pred, names_dev, known, misfits, args.max_misfit, chatbot_self_id, rate)
        pred_key = next((k for k, v in MODELS.items() if v[1] == final.get("version")), None)
        row = {"session": sid, "true_model": MODELS[model][1], "persona_id": persona, "left_out": args.leave_out,
               "probes_answered": sorted(session), "ref_persona": args.ref_persona,
               "expected_developer": DEVELOPER[MODELS[model][0]], "expected_family": exp_fam, "expected_version": exp_ver,
               "pred_developer": DEVELOPER.get(final.get("family")) or names_dev,
               "pred_family": final.get("family"), "pred_version": final.get("version"),
               "judge_family": pred.get("family"), "judge_version": pred.get("version"),
               "family_confidence": pred.get("family_confidence"), "version_confidence": pred.get("version_confidence"),
               "check": args.check, "misfits": misfits, "fit_score": fit, "rule_applied": rule,
               "reason": pred.get("reason"), "names_developer": names_dev, "licence": licences.get(pred_key),
               "family_correct": final.get("family") == exp_fam, "version_correct": final.get("version") == exp_ver}
        if args.domain:
            row["card"] = attach_card(args.domain, pred_key, final.get("family"))
        results.append(row)
        out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
        print(f"[{i}/{len(sessions)}] {row['true_model']:14} {persona:4} | guess {str(row['pred_version']):16} "
              f"{'OK' if row['version_correct'] else 'X '} | fit {fit} | names: {names_dev or '-'}"
              + (f" | rule: {rule}" if rule else ""), flush=True)
        if args.provider != "mock" and not args.rescore:
            time.sleep(args.delay)

    if out:
        out.close()
    n = len(results)
    if not n:
        exit("No results yet.")
    print(f"\nDeveloper accuracy: {sum(r['pred_developer'] == r['expected_developer'] for r in results)}/{n}")
    print(f"Family accuracy:  {sum(r['family_correct'] for r in results)}/{n}")
    print(f"Version accuracy: {sum(r['version_correct'] for r in results)}/{n}")
    unknown = [r for r in results if r["expected_version"] == "Unknown"]
    if unknown:
        print(f"Hidden model called Unknown: {sum(r['pred_version'] == 'Unknown' for r in unknown)}/{len(unknown)}")
    print(f"Rules changed the judge's answer for {sum(bool(r.get('rule_applied')) for r in results)} chatbots")
    for ok in (True, False):
        fits = [r["fit_score"] for r in results if r["version_correct"] == ok and r.get("fit_score") is not None]
        if fits:
            print(f"Fit score when {'right' if ok else 'wrong'}: average {sum(fits) / len(fits):.2f}, lowest {min(fits)}")
    named = [r for r in results if r["names_developer"]]
    print(f"Name detector alone: named a developer for {len(named)}/{n} chatbots, "
          f"correct for {sum(r['names_developer'] == r['expected_developer'] for r in named)}")
    groups = {"banking (BK)": lambda p: p.startswith("BK"), "no persona (P13)": lambda p: p == "P13",
              "other personas": lambda p: not p.startswith("BK") and p != "P13"}
    for g, match in groups.items():
        v = [r["version_correct"] for r in results if match(r["persona_id"])]
        if v:
            print(f"  {g:17} version {sum(v)}/{len(v)}")
    by_model = defaultdict(list)
    for r in results:
        by_model[r["true_model"]].append(r["version_correct"])
    for m, v in sorted(by_model.items()):
        print(f"  {m:14} {sum(v)}/{len(v)} correct")
    print("Most common mistakes:", Counter((r["true_model"], r["pred_version"]) for r in results
                                          if not r["version_correct"]).most_common(3))
    print(f"Saved -> {args.out}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. Results so far are saved; run the same command again to continue.")