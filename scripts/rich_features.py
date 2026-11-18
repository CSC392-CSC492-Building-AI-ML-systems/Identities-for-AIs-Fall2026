"""Hand-built, interpretable response-only features for Experiment 5A.

Syntax group is a set of *heuristics*, not a POS tagger or full parser.
Every feature is computed on a single response with no dataset or label lookup.
"""
from __future__ import annotations

import math
import re
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from stylometry import FEATURE_NAMES as BASIC_NAMES, features_for_text, WORD_RE

EXTRA_GROUPS = {
    'lexical': [
        'repeat_bigram_ratio', 'repeat_trigram_ratio', 'first_person_per_100_words',
        'second_person_per_100_words', 'example_marker_per_100_words',
        'filler_marker_per_100_words', 'contractions_per_100_words',
        'sentence_starter_diversity', 'avg_word_frequency_proxy',
    ],
    'formatting': [
        'blank_lines_per_100', 'list_line_fraction', 'indent_line_fraction',
        'heading_line_fraction', 'code_line_fraction', 'markdown_italics',
        'horizontal_rules', 'blockquotes', 'html_tag_count',
    ],
    'code': [
        'python_keyword_per_100_words', 'function_def_count', 'class_def_count',
        'import_count', 'assignment_line_count', 'comment_line_count',
        'code_digit_fraction', 'bracket_balance_error', 'json_like_flag',
        'shell_prompt_count',
    ],
    'syntax': [
        'comma_clause_proxy', 'subordinate_connector_rate', 'modal_verb_rate',
        'passive_voice_proxy', 'colon_sentence_fraction',
        'parenthetical_phrase_rate', 'sentence_length_std',
        'sentence_length_cv', 'uppercase_sentence_starts_fraction',
    ],
}
BASIC_GROUPS = {
    'lexical': ['avg_word_length','unique_word_ratio','stopword_ratio','long_word_ratio',
                'hedges_per_100_words','refusal_flag'],
    'formatting': ['log_lines','log_paragraphs','code_fences','bullet_lines','numbered_lines',
                   'headings','markdown_bold','markdown_links','pipe_lines','backticks',
                   'curly_braces','square_brackets','latex_markers','newline_per_100_chars'],
    'code': [],
    'syntax': ['avg_sentence_words','sentence_count'],
    'other': [name for name in BASIC_NAMES if name not in {
        'avg_word_length','unique_word_ratio','stopword_ratio','long_word_ratio',
        'hedges_per_100_words','refusal_flag','log_lines','log_paragraphs','code_fences',
        'bullet_lines','numbered_lines','headings','markdown_bold','markdown_links',
        'pipe_lines','backticks','curly_braces','square_brackets','latex_markers',
        'newline_per_100_chars','avg_sentence_words','sentence_count'}],
}
GROUPS = {g: BASIC_GROUPS.get(g, []) + EXTRA_GROUPS.get(g, [])
          for g in ('lexical','formatting','code','syntax','other')}
ALL_NAMES = list(BASIC_NAMES) + [x for g in EXTRA_GROUPS.values() for x in g]
assert len(ALL_NAMES) == len(set(ALL_NAMES))
WORD_SET = set(re.findall(r'\w+', ' '.join(ALL_NAMES)))
MODALS = {'can','could','would','should','might','must','may','will','shall'}
SUBORDINATES = {'because','although','while','whereas','unless','since','whenever','however','therefore'}
PY_KW = {'def','class','return','yield','for','while','if','elif','else','try','except',
         'with','as','import','from','raise','assert','lambda','async','await','pass'}
FIRST = {'i','we','me','my','our','us'}
SECOND = {'you','your','yours'}
EXAMPLE = {'example','examples','e.g','for instance','for example'}
FILLER = {'basically','essentially','simply','just','actually','really'}
SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+|\n(?=\S)')


def more_features(value: str) -> list[float]:
    s = value if isinstance(value, str) else str(value or '')
    words = [t.lower() for t in WORD_RE.findall(s)]
    nw = max(len(words),1)
    nchar = max(len(s),1)
    lines = s.splitlines() or ['']
    nlines = max(len(lines),1)
    stripped_lines = [l.strip() for l in lines]
    sentences = [z.strip() for z in SENTENCE_SPLIT.split(s) if z.strip()]
    if not sentences and s.strip():
        sentences = [s.strip()]
    sentence_sizes = [len(WORD_RE.findall(z)) for z in sentences]
    nsen = max(len(sentences), 1)
    def rate(items, vocabulary):
        return 100 * sum(w in vocabulary for w in items) / nw
    def repeat(n):
        spans = list(zip(*(words[i:] for i in range(n))))
        return (len(spans)-len(set(spans))) / max(len(spans),1)
    first_words = [(WORD_RE.findall(x)[0].lower()) for x in sentences if WORD_RE.findall(x)]
    contraction_count = len(re.findall(r"\b\w+(?:'t|'re|'ve|'ll|'d|'m|'s)\b",s,re.I))
    vals = [
        repeat(2), repeat(3), rate(words,FIRST), rate(words,SECOND),
        100 * len(re.findall(r'\b(?:example|examples|e\.g\.|for instance|for example)\b',s,re.I))/nw,
        rate(words,FILLER),100*contraction_count/nw,
        len(set(first_words))/max(len(first_words),1),
        (sum(len(w) > 9 for w in words)/nw),
    ]
    list_re = re.compile(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)')
    heading_re = re.compile(r'^\s*#{1,6}\s+')
    indent_re = re.compile(r'^(?: {4,}|\t)')
    vals += [
        100 * sum(not x for x in stripped_lines)/nlines,
        sum(bool(list_re.search(l)) for l in lines)/nlines,
        sum(bool(indent_re.search(l)) for l in lines)/nlines,
        sum(bool(heading_re.search(l)) for l in lines)/nlines,
        sum(bool(re.search(r'[=;{}]|\b(?:def|return|import|print)\b',l)) for l in lines)/nlines,
        len(re.findall(r'(?<!\*)\*(?!\*)[^*\n]+\*(?!\*)|_[^_\n]+_',s)),
        len(re.findall(r'^\s*(?:---+|___+)\s*$',s,re.M)),
        len(re.findall(r'^\s*>\s+',s,re.M)),
        len(re.findall(r'</?[A-Za-z][^>]*>',s)),
    ]
    code_chars = ''.join(x for x in lines if any(c in x for c in ('{','}','=',';',':')))
    balance = sum(abs(s.count(a)-s.count(b)) for a,b in [('(',')'),('[',']'),('{','}')])
    vals += [
        rate(words,PY_KW),len(re.findall(r'^\s*(?:async\s+)?def\s+\w+',s,re.M)),
        len(re.findall(r'^\s*class\s+\w+',s,re.M)),
        len(re.findall(r'^\s*(?:from\s+\S+\s+)?import\s+',s,re.M)),
        len(re.findall(r'^\s*\w+(?:\[[^\]]+\])?\s*=(?!=)',s,re.M)),
        len(re.findall(r'^\s*#(?!#)',s,re.M)),
        sum(ch.isdigit() for ch in code_chars)/max(len(code_chars),1),
        float(balance),
        float(bool(re.search(r'^\s*\{\s*["\']\w+["\']\s*:',s,re.M))),
        len(re.findall(r'^\s*(?:\$|>>>|PS>)\s+',s,re.M)),
    ]
    sizes=np.asarray(sentence_sizes,dtype=float)
    vals += [
        s.count(',')/nsen,rate(words,SUBORDINATES),rate(words,MODALS),
        100*len(re.findall(r'\b(?:is|are|was|were|been|be)\s+\w+ed\b',s,re.I))/nw,
        sum(':' in z for z in sentences)/nsen,
        (s.count('(')+s.count(')'))/(2*nsen),
        float(np.std(sizes)) if sizes.size else 0.,
        float(np.std(sizes)/max(float(np.mean(sizes)),1.)) if sizes.size else 0.,
        sum(z[0].isupper() for z in sentences if z)/nsen,
    ]
    return vals


class RichStylometryTransformer(BaseEstimator, TransformerMixin):
    def __init__(self, drop_groups=()):
        self.drop_groups=tuple(drop_groups)

    def fit(self, X, y=None):
        return self

    def get_feature_names_out(self, input_features=None):
        exclusions = {n for grp in self.drop_groups for n in GROUPS[grp]}
        return np.array([n for n in ALL_NAMES if n not in exclusions], dtype=object)

    def transform(self, X):
        allowed = set(self.get_feature_names_out())
        keep=np.array([i for i,n in enumerate(ALL_NAMES) if n in allowed],dtype=int)
        all_rows=[features_for_text(t)+more_features(t) for t in X]
        if not all_rows:
            return np.zeros((0,len(keep)),dtype=float)
        return np.asarray(all_rows,dtype=float)[:,keep]
