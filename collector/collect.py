"""
Data collection script.

Sends each prompt (with its persona/system prompt) to each enabled model, several times,
and saves one record per answer following RESPONSE_FORMAT.md, as JSON Lines.

Everyone runs the same script, so all collected data has the same format.

Examples
    python collect.py --dry-run                       # show what would be sent, call nothing
    python collect.py --model llama3.1-8b --limit 1   # quick test: 1 prompt on 1 model
    python collect.py --model llama3.1-8b             # full run for one model
    python collect.py                                 # all enabled models

Safe to stop and restart: answers already saved are skipped.
"""
import argparse, csv, json, os, random, re, time, uuid, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).parent

# --- Settings (change here or with command-line flags) -----------------------------------
SAMPLES_PER_PROMPT = 3              # answers collected per prompt
# Defaults from V1's collect_data.py. Override per run with --temperature / --max-tokens
# (both are saved in every record).
SEED_BASE = 1000                    # Ollama runs: seed = SEED_BASE + sample_index ...
OLLAMA_NATIVE = "http://localhost:11434"   # for digest/quantization ...
TEMPERATURE = 0.7
MAX_TOKENS = 1200
SUBSET_SEED = 398                   # fixed, so --subset always picks the same prompts
MAX_RETRIES = 5                     # on rate limits / network errors
REFUSAL_PATTERNS = re.compile(
    r"\b(i can(?:'|no)t (?:help|assist|provide|do that)|i(?:'m| am) (?:not able|unable) to|"
    r"i won'?t (?:help|provide)|i must decline|sorry, but i can(?:'|no)t)\b", re.I)
THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.S)   # reasoning text some models emit (e.g. Qwen3)

PROVIDERS = {   # all four accept the same OpenAI-style "chat completions" request
    "ollama":    {"base_url": "http://localhost:11434/v1",                                  "key_env": None},
    "openai":    {"base_url": "https://api.openai.com/v1",                                  "key_env": "OPENAI_API_KEY"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1",                               "key_env": "ANTHROPIC_API_KEY"},
    "google":    {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai",    "key_env": "GEMINI_API_KEY"},
    "mock":      {"base_url": None,                                                         "key_env": None},  # for testing without any model
}


# --- Loading inputs -------------------------------------------------------------------------
def load_prompts(path):
    """Read the prompt file (CSV from the team sheet, or YAML). Returns a list of dicts."""
    path = Path(path)
    if path.suffix in (".yaml", ".yml"):
        rows = yaml.safe_load(open(path, encoding="utf-8"))["prompts"]
        for r in rows:
            r["prompt_id"] = r.get("source_id") or r["id"]
        return rows
    lines = open(path, encoding="utf-8-sig").read().splitlines(True)
    start = next(i for i, l in enumerate(lines) if l.startswith("id,"))  # skip any title row
    rows = list(csv.DictReader(lines[start:]))
    for r in rows:   # use the readable ID (e.g. WC-021) as prompt_id when the sheet has one
        r["prompt_id"] = r.get("source_id") or r["id"]
    return rows


def pick_subset(prompts, n):
    """N prompts from each category (or group, if a prompt has no category), in file order."""
    by_cat = {}
    for p in prompts:
        by_cat.setdefault(p.get("category") or p.get("group") or "none", []).append(p)
    rng = random.Random(SUBSET_SEED)
    keep = set()
    for items in by_cat.values():
        keep.update(id(p) for p in rng.sample(items, min(n, len(items))))
    return [p for p in prompts if id(p) in keep]


def load_personas(path):
    return {p["id"]: (p.get("text") or "") for p in yaml.safe_load(open(path, encoding="utf-8"))["personas"]}


def load_models(path, only=None):
    models = [m for m in yaml.safe_load(open(path, encoding="utf-8"))["models"] if m.get("enabled", True)]
    if not only:   # the mock model only runs when asked for by name
        models = [m for m in models if m["provider"] != "mock"]
    if only:
        models = [m for m in models if m["model_key"] in only]
        missing = set(only) - {m["model_key"] for m in models}
        if missing:
            raise SystemExit(f"Unknown or disabled model(s): {', '.join(sorted(missing))}")
    return models


# --- Calling a model ------------------------------------------------------------------------
def call_model(provider, model_id, system_prompt, user_prompt, temperature, max_tokens, seed=None):
    """Send one request. Returns (text, served_model, finish_reason, in_tokens, out_tokens)."""
    if provider == "mock":
        return (f"[mock answer from {model_id} to: {user_prompt[:40]}]", model_id, "stop", 10, 12)
    cfg = PROVIDERS[provider]
    messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + \
               [{"role": "user", "content": user_prompt}]
    payload = {"model": model_id, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    if seed is not None and provider == "ollama":   # only sent to local Ollama
        payload["seed"] = seed
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if cfg["key_env"]:
        key = os.environ.get(cfg["key_env"])
        if not key:
            raise RuntimeError(f"Missing API key: set {cfg['key_env']} in your .env or environment")
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(cfg["base_url"] + "/chat/completions", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.load(resp)
    choice = data["choices"][0]
    usage = data.get("usage") or {}
    msg = choice["message"]
    text = msg.get("content") or ""
    thinking = msg.get("reasoning") or msg.get("reasoning_content")   # some servers return reasoning separately
    if thinking:
        text = f"<think>{thinking}</think>" + text
    return (text, data.get("model"), choice.get("finish_reason"),
            usage.get("prompt_tokens"), usage.get("completion_tokens"))
 

def call_with_retries(*args):
    for attempt in range(MAX_RETRIES):
        try:
            return call_model(*args), None
        except urllib.error.HTTPError as e:
            retryable = e.code in (429, 500, 502, 503, 504)
            err = f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            retryable, err = True, f"Network error: {e}"
        except Exception as e:  # noqa: BLE001 - record any other failure instead of crashing
            retryable, err = False, f"{type(e).__name__}: {e}"
        if not retryable or attempt == MAX_RETRIES - 1:
            return None, err
        time.sleep(min(60, 2 ** attempt * 2))   # wait 2, 4, 8, 16 s ... then try again


def ollama_model_info(model_id):
    """Get digest and quantization of a local Ollama model. The chat response does not include them,
    so they are asked for separately (once per model per run). Returns None values if unavailable."""
    info = {"model_digest": None, "quantization": None}
    try:
        with urllib.request.urlopen(OLLAMA_NATIVE + "/api/tags", timeout=10) as r:
            for t in json.load(r).get("models", []):
                if t.get("name") in (model_id, model_id + ":latest"):
                    info["model_digest"] = t.get("digest")
        req = urllib.request.Request(OLLAMA_NATIVE + "/api/show", data=json.dumps({"model": model_id}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            info["quantization"] = json.load(r).get("details", {}).get("quantization_level")
    except Exception:   # noqa: BLE001 - best effort, never stop a run for this
        pass
    return info
# --- Main loop ------------------------------------------------------------------------------
def already_saved(out_file):
    """Keys of answers already saved without error, so a restart skips them."""
    done = set()
    if out_file.exists():
        for line in open(out_file, encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not r.get("error"):
                done.add((r["prompt_id"], r["persona_id"], r["sample_index"]))
    return done


def main():
    ap = argparse.ArgumentParser(description="Shared data collection script")
    ap.add_argument("--prompts", default=HERE / "prompts/training_prompts.csv")
    ap.add_argument("--prompt-set-version", default="training_v1")
    ap.add_argument("--personas", default=HERE / "prompts/personas.yaml")
    ap.add_argument("--models", default=HERE / "models.yaml")
    ap.add_argument("--model", action="append", help="only run this model_key (repeatable)")
    ap.add_argument("--persona", action="append",
                    help="run every prompt under this persona instead of the file's persona_id (repeatable)")
    ap.add_argument("--limit", type=int, help="only the first N prompts (for testing)")
    ap.add_argument("--samples", type=int, default=SAMPLES_PER_PROMPT)
    ap.add_argument("--temperature", type=float, action="append",
                    help=f"default {TEMPERATURE}. Give it more than once to cycle per sample, "
                         "e.g. --temperature 0.2 --temperature 0.7 --temperature 1.0")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--subset", type=int,
                    help="only N prompts per category, picked at random with a fixed seed (same every time)")
    ap.add_argument("--run-type", default="library", choices=["library", "baseline", "monitoring"])
    ap.add_argument("--deployment-id", default=None, help="for baseline/monitoring runs, e.g. bank-support-bot")
    ap.add_argument("--tag", default=None, help="label for this round e.g. noon or midnight.")
    ap.add_argument("--out", default=HERE / "data/raw")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env(HERE / ".env")
    prompts = load_prompts(args.prompts)
    if args.subset:
        prompts = pick_subset(prompts, args.subset)
    prompts = prompts[: args.limit]
    temps = args.temperature or [TEMPERATURE]
    personas = load_personas(args.personas)
    models = load_models(args.models, args.model)
    n_personas = len(args.persona) if args.persona else 1
    print(f"{len(prompts)} prompts x {n_personas} persona(s) x {len(models)} models x {args.samples} samples "
          f"= {len(prompts) * n_personas * len(models) * args.samples} answers")

    for m in models:
        name = args.prompt_set_version + (f"__{args.tag}" if args.tag else "")
        out_file = Path(args.out) / m["model_key"] / f"{name}.jsonl"
        info = ollama_model_info(m["model_id"]) if m["provider"] == "ollama" and not args.dry_run \
            else {"model_digest": None, "quantization": None}
        done = already_saved(out_file)
        new = errors = 0
        if not args.dry_run:
            out_file.parent.mkdir(parents=True, exist_ok=True)
        with (open(os.devnull, "w") if args.dry_run else open(out_file, "a", encoding="utf-8")) as f:
            for p in prompts:
                for persona_id in (args.persona or [p.get("persona_id") or "P13"]):
                    if persona_id not in personas:
                        raise SystemExit(f"Prompt {p['prompt_id']} uses unknown persona {persona_id}")
                    for s in range(args.samples):
                        if (p["prompt_id"], persona_id, s) in done:
                            continue
                        temp = temps[s % len(temps)]
                        if args.dry_run:
                            print(f"[dry run] {m['model_key']} | {p['prompt_id']} | {persona_id} | t={temp}")
                            continue
                        t0 = time.time()
                        seed = SEED_BASE + s
                        result, err = call_with_retries(m["provider"], m["model_id"], personas[persona_id],
                                                        p["text"], temp, args.max_tokens, seed)
                        text, served, finish, tin, tout = result or (None, None, None, None, None)
                        reasoning = None
                        if text and THINK_BLOCK.search(text):   # keep reasoning separate from the answer
                            reasoning = "\n".join(THINK_BLOCK.findall(text)).strip()
                            text = THINK_BLOCK.sub("", text).strip()
                        refusal_only = p.get("save_response") == "refusal_only"
                        record = {
                            "record_id": str(uuid.uuid4()),
                            "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "prompt_set_version": args.prompt_set_version,
                            "prompt_id": p["prompt_id"],
                            "prompt_group": p.get("group"),
                            "prompt_category": p.get("category"),
                            "persona_id": persona_id,
                            "sample_index": s,
                            "run_type": args.run_type,
                            "deployment_id": args.deployment_id,
                            "model_key": m["model_key"],
                            "provider": m["provider"],
                            "requested_model": m["model_id"],
                            "served_model": served,
                            "temperature": temp,
                            "max_tokens": args.max_tokens,
                            "response_text": None if refusal_only else text,
                            "reasoning_text": None if refusal_only else reasoning,
                            "refused": bool(REFUSAL_PATTERNS.search(text)) if text else None,
                            "finish_reason": finish,
                            "input_tokens": tin,
                            "output_tokens": tout,
                            "latency_ms": int((time.time() - t0) * 1000),
                            "error": err,
                            #extras
                            "tag": args.tag,
                            "seed": seed if m["provider"] == "ollama" else None,
                            "model_digest": info["model_digest"],
                            "quantization": info["quantization"],
                        }
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        f.flush()
                        new += 1
                        errors += bool(err)
                        if m["provider"] != "ollama" and m.get("delay_seconds"):
                            time.sleep(m["delay_seconds"])   # stay under API rate limits
        print(f"{m['model_key']}: {new} new answers saved ({errors} errors) -> {out_file}")


def load_env(path):
    """Read API keys from a .env file (KEY=value lines). The .env file must never be committed."""
    if path.exists():
        for line in open(path):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"'))


if __name__ == "__main__":
    main()