import html

import streamlit as st
from backend import (get_questions, run_check, collected_answers,
                     available_models, list_deployments,
                     register_chatbot, REGISTER_PERSONAS)

# Persona used to simulate the company chatbot (BK1 = a bank system prompt).
# Must match the persona you used when registering a chatbot for the drift check.
DEMO_PERSONA = "BK1"

# Friendly labels for the 6 probe questions. The exact text sent to the
# chatbot is still shown under "Exact question" and is not changed.
PROBE_LABELS = {
    "LM-01": "Who created you? (wrapped in an injection-style trick)",
    "LM-05": "What is your data cutoff date?",
    "LM-06": "What model are you exactly? (wrapped in an injection-style trick)",
    "I1": "Who created you?",
    "I2": "What is your exact model name and version?",
    "V1-15": "Long writing task (zombie apocalypse essay)",
}

# Plain-language sentence shown under each status.
STATUS_TEXT = {
    "Verified": "This chatbot still matches its approved model.",
    "Identified": "No approved model on file, so this is an identification only.",
    "Drift detected": "The model behind this chatbot no longer matches its approved model.",
    "Needs review": "The answers are unclear. A person should take a look.",
    "Unknown model": "This looks like a model the system has not seen before.",
}
# Which colour each status uses (ok = green, warn = amber, bad = red).
STATUS_CLASS = {
    "Verified": "ok", "Identified": "ok",
    "Needs review": "warn", "Unknown model": "warn",
    "Drift detected": "bad",
}
# What each card level means, in plain words.
LEVEL_TEXT = {
    "version": "Exact model card",
    "family": "Model family card",
    "developer": "Developer card",
    "none": "No card available",
}
FIT_MINIMUM = 0.7   # same threshold the system uses to hand off to the next method

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Model Change Monitor", layout="wide")

# ---------------------------------------------------------------------------
# Styling. This block only changes how things look, not what they do.
# Palette: deep navy for headings, a steady blue for actions, cool grey
# surfaces, and green / amber / red used only for status.
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:wght@600&display=swap');

:root {
  --navy: #0A2342; --blue: #1D4E89; --bg: #F4F6F9; --line: #D9E0E8;
  --text: #1B2A3B; --muted: #5B6B7C;
  --ok: #1E7B4F; --ok-bg: #E8F4EE;
  --warn: #8A5A00; --warn-bg: #FDF3DC;
  --bad: #B42318; --bad-bg: #FDECEA;
  --info-bg: #E8EFF8;
}
html, body, [class*="css"], [data-testid="stAppViewContainer"] {
  font-family: 'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif;
  color: var(--text);
}
[data-testid="stAppViewContainer"] { background: var(--bg); }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }
.block-container { max-width: 1180px; padding-top: 1.5rem; padding-bottom: 4rem; }

/* Sidebar */
[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { font-size: 1rem; color: var(--navy); }

/* Top banner */
.topbar { background: var(--navy); color: #fff; border-radius: 6px; padding: 22px 28px;
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.topbar .name { font-family: 'Source Serif 4', Georgia, serif; font-size: 1.6rem; font-weight: 600; letter-spacing: 0.1px; }
.topbar .sub { color: #B9C7DA; font-size: 0.92rem; margin-top: 2px; }
.topbar .tag { border: 1px solid #5C7396; color: #D5DFEC; border-radius: 4px; padding: 3px 10px; font-size: 0.8rem; }

/* Intro text */
.intro { color: var(--muted); font-size: 0.97rem; max-width: 760px; margin: 14px 0 6px 0; line-height: 1.55; }

/* Numbered steps (they really are a sequence) */
.step { display: flex; align-items: center; gap: 12px; margin: 34px 0 10px 0; }
.step .n { width: 28px; height: 28px; border-radius: 50%; background: var(--blue); color: #fff;
  display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 0.9rem; flex: none; }
.step .t { font-size: 1.2rem; font-weight: 600; color: var(--navy); }
.step .d { color: var(--muted); font-size: 0.92rem; margin-left: 4px; }

/* Question labels above each answer box */
.q { font-weight: 600; color: var(--navy); font-size: 0.95rem; margin: 14px 0 2px 0; }
.q .id { color: var(--muted); font-weight: 500; margin-right: 6px; }

/* Inputs */
/* Text boxes: white box, black text */
textarea, [data-baseweb="textarea"], [data-baseweb="textarea"] > div { background-color: #FFFFFF !important; }
textarea { color: #000000 !important; -webkit-text-fill-color: #000000 !important; caret-color: #000000 !important;
  border-color: var(--line) !important; border-radius: 6px !important;
  font-size: 0.9rem !important; line-height: 1.45 !important; }
textarea:disabled { -webkit-text-fill-color: #000000 !important; opacity: 1 !important; }

/* Dropdowns: white box, black text and a black arrow */
[data-baseweb="select"] > div { background-color: #FFFFFF !important; }
[data-baseweb="select"] * { color: #000000 !important; -webkit-text-fill-color: #000000 !important; }
[data-baseweb="select"] svg { fill: #000000 !important; }
/* The list that opens when you click a dropdown */
[data-baseweb="popover"] ul, [data-baseweb="menu"] { background-color: #FFFFFF !important; }
[data-baseweb="popover"] li, [data-baseweb="popover"] li * { color: #000000 !important; -webkit-text-fill-color: #000000 !important; }
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] li[aria-selected="true"] { background-color: var(--info-bg) !important; }

/* Labels, expanders and code boxes: dark text on light backgrounds */
[data-testid="stWidgetLabel"] p, label p, [data-testid="stCaptionContainer"] { color: var(--text) !important; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color: var(--text) !important; }
[data-testid="stCode"] pre, [data-testid="stCode"] code { background-color: #F4F6F9 !important; }
[data-testid="stCode"] * { color: #1B2A3B !important; }
[data-testid="stExpander"] { background: #fff; border: 1px solid var(--line); border-radius: 6px; }

/* Buttons */
.stButton button { border-radius: 6px; font-weight: 500; padding: 0.55rem 1.3rem; }
.stButton button[kind="primary"] { background: var(--blue); border: 1px solid var(--blue); color: #fff; }
.stButton button[kind="primary"]:hover { background: var(--navy); border-color: var(--navy); color: #fff; }
.stButton button[kind="secondary"] { background: #fff; border: 1px solid var(--blue); color: var(--blue); }
.stButton button[kind="secondary"]:hover { background: var(--info-bg); color: var(--navy); border-color: var(--navy); }

/* Test-mode notice */
.notice { background: var(--warn-bg); color: var(--warn); border-radius: 6px; padding: 10px 14px; font-size: 0.9rem; margin: 8px 0 14px 0; }

/* Result: status banner with the fit score. This is the one bold element. */
.status { display: flex; gap: 32px; align-items: center; justify-content: space-between; flex-wrap: wrap;
  background: #fff; border: 1px solid var(--line); border-left: 8px solid var(--muted);
  border-radius: 6px; padding: 24px 28px; }
.status.ok { border-left-color: var(--ok); background: var(--ok-bg); }
.status.warn { border-left-color: #D69E2E; background: var(--warn-bg); }
.status.bad { border-left-color: var(--bad); background: var(--bad-bg); }
.status .label { font-family: 'Source Serif 4', Georgia, serif; font-size: 2rem; font-weight: 600; color: var(--navy); line-height: 1.1; }
.status.ok .label { color: var(--ok); }
.status.warn .label { color: var(--warn); }
.status.bad .label { color: var(--bad); }
.status .text { margin-top: 6px; color: var(--text); font-size: 1rem; max-width: 480px; }
.fit { min-width: 260px; flex: 1; max-width: 340px; }
.fit .top { display: flex; justify-content: space-between; align-items: baseline; font-size: 0.9rem; color: var(--muted); }
.fit .top b { font-size: 1.5rem; color: var(--navy); font-weight: 600; font-variant-numeric: tabular-nums; }
.bar { position: relative; height: 10px; background: rgba(10,35,66,0.12); border-radius: 5px; margin: 8px 0 6px 0; }
.bar .fill { height: 10px; border-radius: 5px; background: var(--navy); }
.bar .mark { position: absolute; top: -4px; width: 2px; height: 18px; background: var(--navy); opacity: 0.55; }
.fit .note { color: var(--muted); font-size: 0.8rem; }

/* Identification row */
.ident { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; background: #fff;
  border: 1px solid var(--line); border-radius: 6px; margin-top: 16px; }
.ident > div { padding: 16px 22px; border-right: 1px solid var(--line); }
.ident > div:last-child { border-right: none; }
.ident .k { color: var(--muted); font-size: 0.85rem; }
.ident .v { color: var(--navy); font-size: 1.25rem; font-weight: 600; margin-top: 2px; }
@media (max-width: 700px) { .ident { grid-template-columns: 1fr; } .ident > div { border-right: none; border-bottom: 1px solid var(--line); } }

/* Hand-off note */
.handoff { background: var(--info-bg); color: var(--navy); border-radius: 6px; padding: 12px 16px; margin-top: 14px; font-size: 0.93rem; }

/* Model card */
.cardhead { display: flex; align-items: center; gap: 12px; margin: 30px 0 6px 0; }
.cardhead .title { font-size: 1.2rem; font-weight: 600; color: var(--navy); }
.pill { background: var(--info-bg); color: var(--blue); border-radius: 12px; padding: 2px 12px; font-size: 0.82rem; font-weight: 500; }
.cardnote { color: var(--muted); font-size: 0.92rem; margin-bottom: 8px; max-width: 820px; }
.row { display: grid; grid-template-columns: 260px 1fr; gap: 20px; padding: 12px 0; border-bottom: 1px solid var(--line); }
.row:last-child { border-bottom: none; }
.row .name { font-weight: 600; color: var(--navy); font-size: 0.93rem; }
.row .val { font-size: 0.93rem; line-height: 1.5; }
.row .src { color: var(--muted); font-size: 0.82rem; }
@media (max-width: 700px) { .row { grid-template-columns: 1fr; gap: 4px; } }
</style>
"""


def block(markup):
    """Show a piece of HTML. Leading spaces are stripped so Markdown never turns it into a code block."""
    st.markdown("\n".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def esc(value):
    """Make a value safe to put inside HTML."""
    return html.escape(str(value))


def step(number, title, description=""):
    """A numbered section heading."""
    block(f'<div class="step"><div class="n">{number}</div><div class="t">{esc(title)}</div>'
          f'<div class="d">{esc(description)}</div></div>')


block(CSS)

# ---------------------------------------------------------------------------
# Header and intro
# ---------------------------------------------------------------------------
block("""
<div class="topbar">
  <div>
    <div class="name">Model Change Monitor</div>
    <div class="sub">See which AI model is behind a chatbot, and know when it changes.</div>
  </div>
  <div class="tag">Demo</div>
</div>
<div class="intro">
  This demo shows how a bank would connect its chatbot to the identification system.
  Choose a model, let the chatbot answer six questions, and run the check. The system
  names the developer, family and version, and shows the matching model card.
</div>
""")

# ---------------------------------------------------------------------------
# Sidebar settings
# ---------------------------------------------------------------------------
with st.sidebar:
    # NEW: switch between the two pages
    page = st.radio("Page", ["Check a chatbot", "Register a chatbot"])
    st.subheader("Settings")
    # Which domain's card to show
    domain = st.selectbox("Model card view", ["compliance", "governance", "evaluation", "risk"],
                          format_func=str.capitalize)

    # Drift check: pick a chatbot registered with `check_chatbot.py register`.
    # Leave on "None" to only identify the model.
    registered = list_deployments()
    deployment = st.selectbox(
        "Approved chatbot (drift check)",
        [""] + registered,
        format_func=lambda x: x or "None (identify only)",
    )
    if not registered:
        st.caption("No approved chatbots are registered yet. See the README to register one.")

    # Fake judge (free) vs real judge (needs GEMINI_API_KEY in collector/.env)
    test_mode = st.checkbox("Test mode (no API calls)", value=True)

# ---------------------------------------------------------------------------
# Step 1: pick the model behind the chatbot and load its answers
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# NEW: the "Register a chatbot" page.
# Registering saves a chatbot's baseline: how its approved model normally
# answers the six questions. The drift check later compares against it.
# After registering, the chatbot shows up under "Approved chatbot" in the sidebar.
# st.stop() at the end means the Check page below is not drawn on this page.
# ---------------------------------------------------------------------------
if page == "Register a chatbot":
    step(1, "Register an approved chatbot", "Save the model a company approved, so we can spot a swap later.")
    block('<div class="intro">The system records how this model answers the six questions. '
          'Later, the drift check compares a live chatbot against this record and flags any change.</div>')

    # Show the result of the last registration (saved before the page reloaded)
    last = st.session_state.pop("register_result", None)
    if last:
        ok, message = last
        if ok:
            st.success("Chatbot registered. It now appears under Approved chatbot in the sidebar.")
        else:
            st.error(f"Could not register the chatbot. {message}")
        if message:
            with st.expander("Details"):
                st.code(message, language=None)

    reg_name = st.text_input("Chatbot name", placeholder="northshore",
                             help="Letters, numbers, dashes and underscores only.")
    reg_models = available_models()
    reg_model = st.selectbox("Approved model", list(reg_models))
    reg_persona = st.selectbox("System prompt (persona)", REGISTER_PERSONAS,
                               help="BK1 to BK4 are the bank system prompts in our data.")

    exists = reg_name.strip() in list_deployments()
    overwrite = False
    if exists:
        overwrite = st.checkbox("A chatbot with this name already exists. Replace it.")

    if st.button("Register chatbot", type="primary"):
        if not reg_name.strip():
            st.error("Enter a name for the chatbot.")
        elif exists and not overwrite:
            st.error("That name is taken. Tick the box to replace it, or choose another name.")
        else:
            with st.spinner("Registering..."):
                st.session_state["register_result"] = register_chatbot(reg_name, reg_models[reg_model], reg_persona)
            st.rerun()   # reload so the sidebar list includes the new chatbot

    # Chatbots that are already registered
    if list_deployments():
        block('<div class="cardhead"><div class="title">Registered chatbots</div></div>')
        for deployment_name in list_deployments():
            st.markdown(f"- {deployment_name}")
    st.stop()

# ---------------------------------------------------------------------------
# Step 1 of the Check page: pick the model behind the chatbot and load its answers
# ---------------------------------------------------------------------------
step(1, "Choose the chatbot", "Pick the model running behind the company's chatbot.")

models = available_models()
secret = st.selectbox("Model behind the chatbot", list(models))

if st.button("Ask the chatbot six questions"):
    filled = collected_answers(models[secret], persona=DEMO_PERSONA)
    if not filled:
        st.error("No answers found for this model. Check that its data is in collector/data/raw.")
    # Putting the answers in session_state fills the text boxes below
    for pid, text in filled.items():
        st.session_state[pid] = text

# ---------------------------------------------------------------------------
# Step 2: the six questions and the chatbot's answers
# ---------------------------------------------------------------------------
step(2, "Review the answers", "You can also paste in answers from any chatbot.")

questions = get_questions()
answers = {}
left, right = st.columns(2, gap="large")
for index, (pid, q) in enumerate(questions.items()):
    with (left if index % 2 == 0 else right):
        block(f'<div class="q"><span class="id">{esc(pid)}</span>{esc(PROBE_LABELS.get(pid, ""))}</div>')
        with st.expander("Exact question sent to the chatbot"):
            st.code(q, language=None)   # shown literally, so symbols don't get interpreted
        answers[pid] = st.text_area(f"Answer to {pid}", key=pid, height=150, label_visibility="collapsed")


# ---------------------------------------------------------------------------
# Draws the model card: level, note, one tab per domain.
# Family and developer cards list possible values and which models each came
# from; version cards show a single value.
# ---------------------------------------------------------------------------
def show_card(card):
    level = card.get("level", "none")
    block(f'<div class="cardhead"><div class="title">Model card</div>'
          f'<div class="pill">{esc(LEVEL_TEXT.get(level, level))}</div></div>')
    if card.get("note"):
        block(f'<div class="cardnote">{esc(card["note"])}</div>')
    domains = card.get("domains") or []
    if not domains:
        st.write("No card available.")
    else:
        tabs = st.tabs([d.get("title") or d.get("domain") for d in domains])
        for tab, d in zip(tabs, domains):
            with tab:
                rows = ""
                for f in d.get("fields", []):
                    name = f.get("name") or f.get("id")
                    if "values" in f:                       # family/developer card
                        value = "".join(
                            f'<div>{esc(v["value"])} <span class="src">from {esc(", ".join(v["from_models"]))}</span></div>'
                            for v in f["values"])
                    else:                                   # exact-version card
                        value = esc(f.get("value"))
                    rows += f'<div class="row"><div class="name">{esc(name)}</div><div class="val">{value}</div></div>'
                block(rows)
    with st.expander("Raw card data"):
        st.json(card)


# ---------------------------------------------------------------------------
# Step 3: run the check and show the result
# ---------------------------------------------------------------------------
step(3, "Run the check")
if st.button("Check chatbot", type="primary"):
    try:
        with st.spinner("Checking..."):
            res = run_check(answers, domain, deployment or None, test_mode)
    except ValueError as e:        # e.g. fewer than 3 answers filled in
        st.error(f"{e} Fill in at least three answers and try again.")
        st.stop()
    except Exception as e:         # anything else, e.g. missing API key
        st.error(f"The check could not run: {e}")
        st.stop()

    if test_mode:
        block('<div class="notice">Test mode is on. The judge is simulated, so this result is not real detection.</div>')

    # Status banner with the fit score (the main result)
    status = res.get("status", "")
    css_class = STATUS_CLASS.get(status, "warn")
    fit = max(0.0, min(1.0, res.get("fit_score") or 0))
    block(f"""
    <div class="status {css_class}">
      <div>
        <div class="label">{esc(status)}</div>
        <div class="text">{esc(STATUS_TEXT.get(status, ""))}</div>
      </div>
      <div class="fit">
        <div class="top"><span>Fit score</span><b>{fit:.0%}</b></div>
        <div class="bar"><div class="fill" style="width:{fit * 100:.0f}%"></div>
          <div class="mark" style="left:{FIT_MINIMUM * 100:.0f}%"></div></div>
        <div class="note">The line marks the {FIT_MINIMUM:.0%} minimum for a confident result.</div>
      </div>
    </div>
    """)

    # Developer / family / version
    i = res["identified"]
    block(f"""
    <div class="ident">
      <div><div class="k">Developer</div><div class="v">{esc(i["developer"])}</div></div>
      <div><div class="k">Family</div><div class="v">{esc(i["family"])}</div></div>
      <div><div class="k">Version</div><div class="v">{esc(i["version"])}</div></div>
    </div>
    """)

    # Low confidence: the pipeline would pass this to LoRA, then the random forest
    if res.get("handoff_to_next_method"):
        block('<div class="handoff">Confidence is low, so this result would be passed to the next '
              'method in the pipeline (LoRA, then random forest).</div>')

    # Why the system decided this
    reasons = res.get("reasons")
    if reasons:
        with st.expander("Why the system decided this"):
            st.write(reasons if isinstance(reasons, str) else "\n".join(f"- {r}" for r in reasons))

    # The domain card
    show_card(res["card"])