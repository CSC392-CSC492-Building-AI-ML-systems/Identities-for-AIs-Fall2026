import streamlit as st
from backend import get_questions, run_check, collected_answers, VERSION_TO_KEY

# labels for the probe questions. The exact text sent to the
# chatbot is still shown under "Exact question" and is not changed.
PROBE_LABELS = {
    "LM-01": "Who created you? (wrapped in an injection-style trick)",
    "LM-05": "What is your data cutoff date?",
    "LM-06": "What model are you exactly? (wrapped in an injection-style trick)",
    "I1": "Who created you?",
    "I2": "What is your exact model name and version?",
    "V1-15": "Long writing task (zombie apocalypse essay)",
}

st.set_page_config(page_title="Model Change Monitor", layout="wide")
st.title("Model Change Monitor (demo)")
st.caption("Demo client: shows how a company would plug into the identification system.")

st.markdown(
    """
**How to use this demo**
1. In the **left sidebar**, choose which domain card you want to see (compliance, governance, evaluation or risk).
2. Choose the model that is running behind the company's chatbot, then click **Ask the chatbot the 6 questions**. The answers below fill in automatically.
3. Click **Check chatbot** at the bottom.

**What should happen:** the system reads the answers, works out the developer, family and version of the model that wrote them, and shows how well the answers fit (fit score). It then shows that model's card for the domain you chose. If it can't tell the exact version, it shows the most specific card it can, or asks for review.
"""
)

with st.sidebar:
    domain = st.selectbox("Domain card", ["compliance", "governance", "evaluation", "risk"])
    # REMOVED (drift check needs a registered baseline, not set up yet):
    # deployment = st.text_input("Registered chatbot name (optional, checks for drift)")
    deployment = ""
    test_mode = st.checkbox("Test mode (fake judge, no API calls)", value=True)

st.subheader("Simulated company chatbot")
secret = st.selectbox("Model currently running behind the chatbot", list(VERSION_TO_KEY))
if st.button("Ask the chatbot the 6 questions"):
    filled = collected_answers(VERSION_TO_KEY[secret])
    if not filled:
        st.error("No collected answers found for that model.")
    for pid, text in filled.items():
        st.session_state[pid] = text

st.divider()

questions = get_questions()
answers = {}
for pid, q in questions.items():
    st.markdown(f"**{pid}: {PROBE_LABELS.get(pid, '')}**")
    with st.expander("Exact question sent to the chatbot"):
        st.code(q, language=None)   # shown literally, so symbols don't get interpreted
    answers[pid] = st.text_area(f"Answer to {pid}", key=pid, label_visibility="collapsed")


def show_card(card):
    st.subheader("Model card")
    st.caption(f"Level: {card.get('level', 'unknown')}")
    if card.get("note"):
        st.info(card["note"])
    domains = card.get("domains") or []
    if not domains:
        st.write("No card available.")
    else:
        tabs = st.tabs([d.get("title") or d.get("domain") for d in domains])
        for tab, d in zip(tabs, domains):
            with tab:
                for f in d.get("fields", []):
                    name = f.get("name") or f.get("id")
                    if "values" in f:                      # family/developer card
                        st.markdown(f"**{name}**")
                        for v in f["values"]:
                            st.write(f"- {v['value']} (from {', '.join(v['from_models'])})")
                    else:                                  # exact-version card
                        st.markdown(f"**{name}:** {f.get('value')}")
    with st.expander("Raw card data"):
        st.json(card)


if st.button("Check chatbot", type="primary"):
    try:
        with st.spinner("Checking..."):
            res = run_check(answers, domain, deployment.strip() or None, test_mode)
    except ValueError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:
        st.error(f"The system returned an error: {e}")
        st.stop()

    status = res.get("status", "")
    if status in ("Verified", "Identified"):
        st.success(status)
    elif status == "Drift detected":
        st.error("DRIFT DETECTED: this chatbot no longer matches its approved model.")
    else:
        st.warning(status)
    if test_mode:
        st.caption("Test mode: the judge is fake, so this result is not real detection.")

    i = res["identified"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Developer", i["developer"])
    c2.metric("Family", i["family"])
    c3.metric("Version", i["version"])
    c4.metric("Fit score", f"{res['fit_score']:.0%}")
    if res.get("handoff_to_next_method"):
        st.info("Handed off to the next method (LoRA / random forest): low confidence here.")
    reasons = res.get("reasons")
    if reasons:
        st.write(reasons if isinstance(reasons, str) else "\n".join(f"- {r}" for r in reasons))

    show_card(res["card"])


# ---------------------------------------------------------------------------
# OLD VERSION
# ---------------------------------------------------------------------------
# declared = st.selectbox("Model the company says it uses", list(VERSION_TO_KEY))
# source = st.selectbox("Load a real answer written by", list(VERSION_TO_KEY))
# if st.button("Load sample answer"):
#     st.session_state["answer"] = sample_answer(VERSION_TO_KEY[source])
# answer = st.text_area("Paste a chatbot answer here", key="answer")
# if st.button("Check") and answer:
#     result = identify(answer)
#     if result["version"] != declared:
#         st.error(f"MISMATCH: declared {declared}, detected {result['version']}")
#     else:
#         st.success("Matches the declared model")
#     col1, col2 = st.columns(2)
#     col1.metric("Family", result["family"], f"{result['family_confidence']:.0%}")
#     col2.metric("Version", result["version"], f"{result['version_confidence']:.0%}")
#     st.caption(result["reason"])
#     st.subheader("Model card")
#     st.json(get_card(result))