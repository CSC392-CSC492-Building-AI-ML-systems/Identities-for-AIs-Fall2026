"""Optional sentence-transformers feature extractor for Experiment 5A.
First use downloads a pretrained model. Saves model *identifier*, not model weights.
"""
from __future__ import annotations
import numpy as np
from sklearn.base import BaseEstimator,TransformerMixin

class SentenceEmbeddingTransformer(BaseEstimator,TransformerMixin):
    def __init__(self, model_name='sentence-transformers/all-MiniLM-L6-v2',batch_size=32):
        self.model_name=model_name
        self.batch_size=batch_size

    def fit(self,X,y=None):
        return self

    def transform(self,X):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError('Install optional dependency: pip install sentence-transformers') from exc
        if not hasattr(self,'_encoder'):
            self._encoder=SentenceTransformer(self.model_name)
        return np.asarray(self._encoder.encode(list(X), batch_size=self.batch_size,
                                                 show_progress_bar=False,normalize_embeddings=True),dtype=np.float64)

    def __getstate__(self):
        state=self.__dict__.copy()
        state.pop('_encoder',None)
        return state
