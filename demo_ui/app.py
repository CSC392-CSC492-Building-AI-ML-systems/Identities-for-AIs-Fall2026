import streamlit as st
from backend import identify, get_card, sample_answer, VERSION_TO_KEY

st.title("Model Change Monitor (demo)")

declared = st.selectbox("Model the company says it uses", list(VERSION_TO_KEY))

source = st.selectbox("Load a real answer written by", list(VERSION_TO_KEY))
if st.button("Load sample answer"):
    st.session_state["answer"] = sample_answer(VERSION_TO_KEY[source])

answer = st.text_area("Paste a chatbot answer here", key="answer")

if st.button("Check") and answer:
    result = identify(answer)

    if result["version"] != declared:
        st.error(f"MISMATCH: declared {declared}, detected {result['version']}")
    else:
        st.success("Matches the declared model")

    col1, col2 = st.columns(2)
    col1.metric("Family", result["family"], f"{result['family_confidence']:.0%}")
    col2.metric("Version", result["version"], f"{result['version_confidence']:.0%}")
    st.caption(result["reason"])

    st.subheader("Model card")
    st.json(get_card(result))
