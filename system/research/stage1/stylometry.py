"""Small interpretable feature extractor; no target labels or metadata are inputs."""
from __future__ import annotations

import math
import re
import string
from collections import Counter

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)
SENTENCE_RE = re.compile(r'[.!?]+(?=\s|$)')
FENCED_CODE = re.compile(r'^\s*```', re.MULTILINE)
BULLET_RE = re.compile(r'^\s*[-*+]\s+', re.MULTILINE)
NUMBERED_RE = re.compile(r'^\s*\d+[.)]\s+', re.MULTILINE)
HEADER_RE = re.compile(r'^\s*#{1,6}\s+\S', re.MULTILINE)
LINK_RE = re.compile(r'\[[^\]]+\]\([^)]+\)')
MARKDOWN_BOLD_RE = re.compile(r'\*\*[^*\n]+\*\*')
HEDGE_RE = re.compile(r'\b(?:perhaps|possibly|probably|might|may|likely|uncertain|typically)\b', re.I)
REFUSAL_RE = re.compile(r"\b(?:i cannot|i can't|i am unable|i'm unable|sorry,? but)\b", re.I)
STOPWORDS = frozenset('a an and are as at be but by for from had has have he her here his i if in is it its of on or our she that the their them there these they this those to was we were what when where which who will with you your'.split())

FEATURE_NAMES = [
    'log_chars', 'log_words', 'log_lines', 'log_paragraphs',
    'avg_word_length', 'avg_sentence_words', 'sentence_count',
    'unique_word_ratio', 'stopword_ratio', 'long_word_ratio',
    'uppercase_ratio', 'digit_ratio', 'whitespace_ratio',
    'comma_per_100', 'period_per_100', 'colon_per_100',
    'semicolon_per_100', 'exclamation_per_100', 'question_per_100',
    'quote_per_100', 'paren_per_100', 'dash_per_100',
    'code_fences', 'bullet_lines', 'numbered_lines', 'headings',
    'markdown_bold', 'markdown_links', 'pipe_lines',
    'backticks', 'curly_braces', 'square_brackets', 'latex_markers',
    'hedges_per_100_words', 'refusal_flag', 'newline_per_100_chars',
]


def features_for_text(value: str) -> list[float]:
    text = value if isinstance(value, str) else str(value or '')
    words = WORD_RE.findall(text)
    lower = [w.lower() for w in words]
    wc = len(words)
    nc = len(text)
    lines = text.splitlines() or ['']
    nonempty_paragraphs = [x for x in re.split(r'\n\s*\n', text.strip()) if x.strip()]
    alpha = sum(ch.isalpha() for ch in text)
    num_sentences = len(SENTENCE_RE.findall(text))
    if not num_sentences and wc:
        num_sentences = 1

    def per100(ch: str) -> float:
        return 100.0 * text.count(ch) / max(nc, 1)

    values = [
        math.log1p(nc), math.log1p(wc), math.log1p(len(lines)),
        math.log1p(len(nonempty_paragraphs)),
        sum(len(w) for w in words) / max(wc, 1),
        wc / max(num_sentences, 1), float(num_sentences),
        len(set(lower)) / max(wc, 1),
        sum(w in STOPWORDS for w in lower) / max(wc, 1),
        sum(len(w) >= 8 for w in words) / max(wc, 1),
        sum(ch.isupper() for ch in text) / max(alpha, 1),
        sum(ch.isdigit() for ch in text) / max(nc, 1),
        sum(ch.isspace() for ch in text) / max(nc, 1),
        per100(','), per100('.'), per100(':'), per100(';'),
        per100('!'), per100('?'), per100('"') + per100("'"),
        per100('(') + per100(')'), per100('-'),
        float(len(FENCED_CODE.findall(text))),
        float(len(BULLET_RE.findall(text))),
        float(len(NUMBERED_RE.findall(text))),
        float(len(HEADER_RE.findall(text))),
        float(len(MARKDOWN_BOLD_RE.findall(text))),
        float(len(LINK_RE.findall(text))),
        float(sum(line.count('|') >= 2 for line in lines)),
        float(text.count('`')),
        float(text.count('{') + text.count('}')),
        float(text.count('[') + text.count(']')),
        float(text.count('\\(') + text.count('\\[') + text.count('$$')),
        100.0 * len(HEDGE_RE.findall(text)) / max(wc, 1),
        float(bool(REFUSAL_RE.search(text))),
        per100('\n'),
    ]
    assert len(values) == len(FEATURE_NAMES)
    return values


class StylometryTransformer(BaseEstimator, TransformerMixin):
    """Sklearn-compatible; accepts an iterable of response strings."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return np.asarray([features_for_text(t) for t in X], dtype=np.float64)

    def get_feature_names_out(self, input_features=None):
        return np.array(FEATURE_NAMES, dtype=object)
