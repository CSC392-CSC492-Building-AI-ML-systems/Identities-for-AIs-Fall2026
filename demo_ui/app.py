import streamlit as st
from backend import identify, get_card

st.title("Model Change Monitor (demo)")

declared = st.selectbox("Model the company says it uses",
                        ["Llama 3.1 8B", "Qwen3 8B", "Gemma 3 4B"])
answer = st.text_area("Paste a chatbot answer here")

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