"""Multi-probe RF identifier. Candidate-only until open-set calibration."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from . import rf_panel_features as features
from ..schemas import IdentificationResult, ProbeQuestion

class RandomForestPanelIdentifier:
    name='random_forest'
    def __init__(self,manifest,*,predictor=None):
        self.manifest=manifest; o=manifest.options
        if manifest.adapter!='random_forest' or manifest.stage!=2 or o.get('feature_abi')!=features.FEATURE_ABI:
            raise ValueError('Invalid RF panel ABI')
        if o.get('acceptance_policy')!={'mode':'review_only'}:
            raise ValueError('Panel RF requires review_only until calibrated')
        self.labels=tuple(o.get('label_order',[]))
        if len(self.labels)<2 or len(set(self.labels))!=len(self.labels) or set(self.labels)!=set(manifest.supported_models):
            raise ValueError('Panel RF labels mismatch')
        spec=json.loads((manifest.directory/'feature_manifest.json').read_text(encoding='utf-8'))
        panel=spec.get('probes'); ids=o.get('probe_ids')
        if not isinstance(panel,list) or not isinstance(ids,list) or not 1<=len(ids)<=30 or len(set(ids))!=len(ids):
            raise ValueError('Invalid panel definition')
        self._probes=tuple(ProbeQuestion(p['id'],p['text']) for p in panel)
        if list(ids)!=[p.probe_id for p in self._probes] or spec.get('feature_columns')!=features.columns(ids) or spec.get('target')!='model_key':
            raise ValueError('Panel feature order mismatch')
        self.ids=tuple(ids); self.columns=features.columns(ids); self._predictor=predictor
    def required_probes(self):return self._probes
    def _load(self):
        import joblib, sklearn
        from . import rf_features
        root=self.manifest.directory
        expected={e.relative_path:e.sha256 for e in self.manifest.required_files}
        if not {'classifier.joblib','feature_manifest.json','feature_extractor.py','base_text_features.py'}<=expected.keys():
            raise ValueError('Panel RF payload missing')
        for name,sha in expected.items():
            p=(root/name).resolve()
            if not p.is_relative_to(root.resolve()) or not p.is_file() or not sha or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
                raise ValueError('Panel RF checksum mismatch')
        if (root/'feature_extractor.py').read_bytes()!=Path(features.__file__).read_bytes() or (root/'base_text_features.py').read_bytes()!=Path(rf_features.__file__).read_bytes():
            raise ValueError('Panel RF installed feature implementation differs')
        if sklearn.__version__!=self.manifest.options.get('sklearn_version'):
            raise ValueError('Panel RF sklearn version mismatch')
        model=joblib.load(root/'classifier.joblib')  # trusted candidate only
        if list(model.classes_)!=list(self.labels) or list(model.feature_names_in_)!=self.columns:
            raise ValueError('Panel RF estimator contract mismatch')
        model.n_jobs=1
        return lambda frame: dict(zip(self.labels,map(float,model.predict_proba(frame)[0])))
    def identify(self,context):
        start=perf_counter(); answers={}
        for p in self._probes:
            if p.probe_id not in context.probes:
                raise ValueError(f'Missing RF probe {p.probe_id}')
            obs=context.probes[p.probe_id]
            if obs.prompt_id not in (None,p.probe_id) or obs.prompt_text!=p.prompt_text:
                raise ValueError('RF probe identity/text mismatch')
            answers[p.probe_id]=obs.response_text
        if self._predictor is None:self._predictor=self._load()
        scores=dict(self._predictor(features.frame([answers],self.ids)))
        if set(scores)!=set(self.labels) or any(not isinstance(x,(float,int)) or not math.isfinite(x) or not 0<=x<=1 for x in scores.values()) or abs(sum(scores.values())-1)>1e-3:
            raise ValueError('Invalid panel probabilities')
        candidate=max(self.labels,key=lambda k:scores[k])
        return IdentificationResult(method=self.name,outcome='unknown',candidate_model_id=candidate,score=float(scores[candidate]),score_type='rf_panel_predict_proba',handoff_requested=True,model_scores=scores,probe_ids_used=list(self.ids),reason='Closed-set multi-probe candidate; not an accepted identity',duration_ms=(perf_counter()-start)*1000,diagnostics={'artifact_id':self.manifest.artifact_id,'closed_set':True,'feature_abi':features.FEATURE_ABI,'acceptance_policy':'review_only','blank_probe_count':sum(not t.strip() for t in answers.values())})
