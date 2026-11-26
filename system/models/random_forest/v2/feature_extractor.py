"""Versioned, text-only multi-probe feature ABI; training and inference share it.

Probe slots are ordered by the selected panel, not by arrival order. No model
IDs, routing/provider fields, latency, tokens, persona, or collector flags.
Hashing is fixed and stateless; all lexical features come from visible text.
"""
from __future__ import annotations
from .rf_features import response_features, TEXT_FEATURES

FEATURE_ABI = 'fingerprint_rf_panel_text_v1'
HASH_DIM = 128
FEATURES = tuple(TEXT_FEATURES) + ('blank_response',) + tuple(f'wordhash_{i}' for i in range(HASH_DIM)) + tuple(f'charhash_{i}' for i in range(HASH_DIM))


def text_vector(text):
    from sklearn.feature_extraction.text import HashingVectorizer
    if text is None:
        text = ''
    if not isinstance(text,str):
        raise ValueError('Response text must be string or null')
    text = text.replace('\r\n','\n').replace('\r','\n')
    stats=response_features(text)
    out=[float(stats[k]) for k in TEXT_FEATURES]+[float(not text.strip())]
    for analyzer,ngram in [('word',(1,2)),('char',(3,5))]:
        vec=HashingVectorizer(n_features=HASH_DIM,analyzer=analyzer,ngram_range=ngram,alternate_sign=False,norm='l2',lowercase=True)
        out.extend(vec.transform([text]).toarray()[0].tolist())
    return out


def columns(probe_ids):
    return [f'{pid}::{f}' for pid in probe_ids for f in FEATURES]


def frame(sessions, probe_ids):
    import pandas as pd
    if not probe_ids or len(set(probe_ids))!=len(probe_ids):
        raise ValueError('Expected unique nonempty probe panel')
    return pd.DataFrame([[x for pid in probe_ids for x in text_vector(answers[pid])] for answers in sessions],columns=columns(probe_ids))
