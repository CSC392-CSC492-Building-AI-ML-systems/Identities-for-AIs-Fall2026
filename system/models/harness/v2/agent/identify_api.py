"""Narrow v2 identification entry; backend owns deployment history and cards."""
from types import SimpleNamespace
import check_chatbot
from probe_identify import DEFAULT_PROBES

def identify(answers, domain=None, deployment=None, judge_provider="google", judge_model="gemini-3.8-flash", handoff_below=0.7):
    if deployment is not None: raise ValueError("Use backend deployment history")
    if not isinstance(answers,dict) or set(answers)!=set(DEFAULT_PROBES) or any(not isinstance(a,str) for a in answers.values()):
        raise ValueError("All six string answers required; blanks are valid observations")
    session={p:answers[p] if answers[p].strip() else "" for p in DEFAULT_PROBES}
    args=SimpleNamespace(judge_provider=judge_provider,judge_model=judge_model,handoff_below=handoff_below)
    return check_chatbot.identify_answers(session,args)
