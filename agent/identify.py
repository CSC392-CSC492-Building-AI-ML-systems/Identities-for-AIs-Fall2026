"""
Agentic model identifier (Stage 2, harness approach), first version.

Given one chatbot answer and the prompt that produced it, an LLM (e.g. Gemini) guesses which model
wrote it. The "harness" gives the LLM context: example answers from every known model to the SAME
prompt, taken from our collected fingerprinting data. It then returns family, version, confidence
and a reason, and attaches the predicted model's licence info (a first "tool": model card lookup).

Evaluation: answers with sample_index 0 and 1 are the example pool; sample_index 2 is the test set,
so the LLM is never tested on an answer it was shown.

Examples
    python identify.py --dry-run --limit 1          # print the context that would be sent, call nothing
    python identify.py --provider mock --limit 5    # test the pipeline with a fake LLM
    python identify.py --limit 20                   # real run on 20 test answers (Gemini free tier)
"""
import argparse, csv, json, os, random, re, time, urllib.request, urllib.error
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parent / "collector" / "data" / "raw"          # where collect.py saved the answers
LICENCES = HERE.parent / "collector" / "licences.yaml"

# Our model keys -> family and readable version (Stage 2 output fields in the backend plan)
MODELS = {
    "llama3.1-8b": ("Llama", "Llama 3.1 8B"),
    "llama3.2-3b": ("Llama", "Llama 3.2 3B"),
    "qwen3-8b":    ("Qwen", "Qwen3 8B"),
    "qwen3.5-9b":  ("Qwen", "Qwen3.5 9B"),
    "gemma3-4b":   ("Gemma", "Gemma 3 4B"),
    "gemini-3.8-flash": ("Gemini", "Gemini 3.8 Flash"),
    "gemini-3.1-pro":   ("Gemini", "Gemini 3.1 Pro"),
}
DATASETS = {"fingerprint": "fingerprint_v0.jsonl", "training": "training_v1.jsonl"}
PROVIDERS = {
    "google":    ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "openai":    ("https://api.openai.com/v1", "OPENAI_API_KEY"),
}
MAX_EXAMPLE_CHARS = 600      # cut long example answers so the context stays small (and cheap)

INSTRUCTIONS = """You identify which AI model wrote a chatbot answer.
You are given the prompt, examples of how each known model answered that same prompt, and the answer to identify.
Compare wording, tone, length, formatting, self-descriptions and refusal style.
Known models: {models}.
If the answer does not clearly match any known model, use "Unknown".
Reply with JSON only, no other text:
{{"family": "<{families}|Unknown>", "version": "<one of the known versions or Unknown>",
  "family_confidence": <0-1>, "version_confidence": <0-1>, "reason": "<one sentence>"}}"""


def load_records(models, datasets):
    recs = []
    for key in models:
        for ds in datasets:
            f = DATA / key / DATASETS[ds]
            if f.exists():
                for r in map(json.loads, open(f, encoding="utf-8")):
                    if not r.get("error") and r.get("response_text"):
                        r["_data"] = ds
                        recs.append(r)
    return recs


def load_prompt_texts(datasets):
    texts = {}
    pdir = HERE.parent / "collector" / "prompts"
    try:
        import yaml
        if "fingerprint" in datasets:
            for p in yaml.safe_load(open(pdir / "fingerprinting_prompts.yaml", encoding="utf-8"))["prompts"]:
                texts[("fingerprint", p["id"])] = p["text"]
    except Exception:
        pass
    if "training" in datasets:
        try:
            lines = open(pdir / "training_prompts.csv", encoding="utf-8-sig").read().splitlines(True)
            start = next(i for i, l in enumerate(lines) if l.startswith("id,"))
            for r in csv.DictReader(lines[start:]):
                texts[("training", r.get("source_id") or r["id"])] = r["text"]
        except Exception:
            pass
    return texts


def build_messages(test, pool, models):
    """Context = each model's example answers to the same prompt, under the same persona if possible."""
    parts = [f"PROMPT:\n{test['prompt_text']}\n"]
    for key in models:
        ex = [r for r in pool if r["model_key"] == key and r["prompt_id"] == test["prompt_id"]
              and r["_data"] == test["_data"]]        
        same_persona = [r for r in ex if r["persona_id"] == test["persona_id"]]
        for r in (same_persona or ex)[:2]:
            parts.append(f"EXAMPLE from {MODELS[key][1]}:\n{r['response_text'][:MAX_EXAMPLE_CHARS]}\n")
    parts.append(f"ANSWER TO IDENTIFY:\n{test['response_text'][:MAX_EXAMPLE_CHARS * 2]}")
    families = sorted({MODELS[k][0] for k in models})
    system = INSTRUCTIONS.format(models=", ".join(MODELS[k][1] for k in models), families="|".join(families))    
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(parts)}]


def call_llm(provider, model, messages):
    if provider == "mock":   # random guess, for testing the pipeline
        fam, ver = random.choice(list(MODELS.values()))
        return json.dumps({"family": fam, "version": ver, "family_confidence": 0.5,
                           "version_confidence": 0.3, "reason": "mock"})
    base, key_env = PROVIDERS[provider]
    key = os.environ.get(key_env) or exit(f"Set {key_env} in your environment or .env")
    body = json.dumps({"model": model, "messages": messages, "temperature": 0}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise RuntimeError(f"HTTP {e.code}: {e.read()[:200].decode(errors='replace')}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt == 4:
                raise RuntimeError(f"Network error: {e}")
        print(f"  (busy or slow, retrying in {10 * (attempt + 1)}s)", flush=True)
        time.sleep(10 * (attempt + 1))   # free tier: wait and retry


def parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def licence_lookup():
    """Tool: model_key -> licence name, from the compliance card's licences.yaml."""
    try:
        import yaml
        lic = yaml.safe_load(open(LICENCES, encoding="utf-8"))["licences"]
        return {k: l["name"] for l in lic for k in l.get("applies_to", [])}
    except Exception:
        return {}


def load_env(path):
    if path.exists():
        for line in open(path):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="google", choices=["google", "anthropic", "openai", "mock"])
    ap.add_argument("--model", default="gemini-3.8-flash")
    ap.add_argument("--data", default="fingerprint", choices=["fingerprint", "training", "both"])
    ap.add_argument("--limit", type=int, default=20, help="number of test answers")
    ap.add_argument("--per-model", type=int, help="this many test answers from EACH model")
    ap.add_argument("--delay", type=float, default=4, help="seconds between calls (free tier)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    datasets = ["fingerprint", "training"] if args.data == "both" else [args.data]
    if not args.out:
        args.out = HERE / ("results.jsonl" if args.data == "fingerprint" else f"results_{args.data}.jsonl")
    load_env(HERE.parent / "collector" / ".env")

    prompts = load_prompt_texts(datasets)

    recs = load_records(MODELS, datasets)
    models = sorted({r["model_key"] for r in recs})
    if not recs:
        exit(f"No {args.data} data found under {DATA}")
    for r in recs:
        r["prompt_text"] = prompts.get((r["_data"], r["prompt_id"]), f"(prompt {r['prompt_id']})")
    pool = [r for r in recs if r["sample_index"] in (0, 1)]
    tests = [r for r in recs if r["sample_index"] == 2]
    random.Random(398).shuffle(tests)
    if args.per_model:
        seen = Counter()
        picked = []
        for t in tests:
            if seen[t["model_key"]] < args.per_model:
                seen[t["model_key"]] += 1
                picked.append(t)
        tests = picked
        random.Random(398).shuffle(tests)
    else:
        tests = tests[: args.limit]
    
    licences = licence_lookup()
    done = {}                                  # resume: keep answers already scored in this file
    if Path(args.out).exists() and not args.dry_run:
        done = {r["record_id"]: r for r in map(json.loads, open(args.out, encoding="utf-8"))}
        if done:
            print(f"Continuing: {len(done)} already scored in {args.out}")
    out = None if args.dry_run else open(args.out, "a", encoding="utf-8")
    results = [done[t["record_id"]] for t in tests if t["record_id"] in done]
    for i, t in enumerate(tests, 1):
        if t["record_id"] in done:
            continue
        msgs = build_messages(t, pool, models)
        if args.dry_run:
            print(msgs[0]["content"], "\n---\n", msgs[1]["content"])
            return
        try:
            pred = parse(call_llm(args.provider, args.model, msgs))
        except RuntimeError as e:
            print(f"[{i}/{len(tests)}] skipped ({e}); run the same command again to retry it")
            continue
        true_fam, true_ver = MODELS[t["model_key"]]
        pred_key = next((k for k, v in MODELS.items() if v[1] == pred.get("version")), None)
        row = {"record_id": t["record_id"], "prompt_id": t["prompt_id"], "persona_id": t["persona_id"],
               "true_model": true_ver, "pred_family": pred.get("family"), "pred_version": pred.get("version"),
               "family_confidence": pred.get("family_confidence"), "version_confidence": pred.get("version_confidence"),
               "reason": pred.get("reason"), "licence": licences.get(pred_key),
               "family_correct": pred.get("family") == true_fam, "version_correct": pred.get("version") == true_ver}
        results.append(row)
        out.write(json.dumps(row) + "\n"); out.flush()   # saved straight away, so nothing is lost
        print(f"[{i}/{len(tests)}] true {true_ver:14} | guess {str(pred.get('version')):14} "
              f"{'OK' if row['version_correct'] else 'X '} | {t['prompt_id']} {t['persona_id']}", flush=True)
        if args.provider != "mock":
            time.sleep(args.delay)

    out.close()
    n = len(results)
    if not n:
        exit("No results yet.")
    print(f"\nFamily accuracy:  {sum(r['family_correct'] for r in results)}/{n}")
    print(f"Version accuracy: {sum(r['version_correct'] for r in results)}/{n}")
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