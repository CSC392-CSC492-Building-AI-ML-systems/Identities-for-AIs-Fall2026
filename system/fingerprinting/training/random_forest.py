"""Train closed-set RF candidates over fixed multi-probe traces.

Implements LLMmap Appendix C's greedy subset search with an RF backbone,
not LLMmap's embedding/self-attention classifier. Selection is validation-only.
"""
from __future__ import annotations
import json
import shutil
import sys
from collections import Counter,defaultdict
from pathlib import Path
from ..adapters import rf_features, rf_panel_features as features
from ..onboarding import artifacts as a, datasets as d


def load_traces(path, probe_ids, prompt_set):
    """Group library records, never fabricate missing responses."""
    groups={}; ids=set()
    for _,r,_ in d.read_rows(path):
        if r.get('error') is not None or r.get('prompt_set_version')!=prompt_set or r.get('prompt_id') not in probe_ids:
            raise ValueError('Unexpected row in fixed panel export')
        rid=r['record_id']
        if rid in ids:raise ValueError('Repeated record ID')
        ids.add(rid)
        if r.get('run_type')!='library' or r.get('deployment_id') is not None or type(r.get('sample_index')) is not int:
            raise ValueError('Require library sample groups')
        key=(r['model_key'],r['persona_id'],r['sample_index'])
        t=groups.setdefault(key,{'model_id':key[0],'persona_id':key[1],'sample_index':key[2],'answers':{},'record_ids':{},'configuration':(r.get('temperature'),r.get('max_tokens'))})
        if t['configuration']!=(r.get('temperature'),r.get('max_tokens')) or r['prompt_id'] in t['answers']:
            raise ValueError('Ambiguous probe group')
        t['answers'][r['prompt_id']]=r['response_text'] or ''
        t['record_ids'][r['prompt_id']]=rid
    if not groups or any(set(t['answers'])!=set(probe_ids) for t in groups.values()):
        raise ValueError('Incomplete fixed panel trace')
    return [groups[k] for k in sorted(groups)]


def matrices(traces, pool):
    return features.frame([t['answers'] for t in traces],pool)


def metrics(truth,pred,labels):
    from sklearn.metrics import accuracy_score,f1_score,confusion_matrix,classification_report
    return {'traces':len(truth),'accuracy':float(accuracy_score(truth,pred)),
            'macro_f1':float(f1_score(truth,pred,labels=labels,average='macro',zero_division=0)),
            'class_counts':dict(Counter(truth)), 'labels':list(labels),
            'confusion_matrix':confusion_matrix(truth,pred,labels=labels).tolist(),
            'classification_report':classification_report(truth,pred,labels=labels,output_dict=True,zero_division=0)}


def fit_greedy(train,validation,pool,*,budget,estimators=100,seed=42,min_samples_leaf=1,max_depth=None):
    """Train every candidate extension on train; choose by validation accuracy.

    Ties: macro-F1, then probe ID. Budget is set before seeing test results.
    """
    from sklearn.ensemble import RandomForestClassifier
    if not 1<=budget<=len(pool):raise ValueError('Invalid probe budget')
    labels=sorted({t['model_id'] for t in train})
    if len(labels)<2 or set(labels)!={t['model_id'] for t in validation}:
        raise ValueError('Training/validation classes must match')
    if {t['persona_id'] for t in train}&{t['persona_id'] for t in validation}:
        raise ValueError('Persona leakage between training and validation')
    x=matrices(train,pool); v=matrices(validation,pool)
    y=[t['model_id'] for t in train]; vy=[t['model_id'] for t in validation]
    chosen=[]; rounds=[]; winner=None
    for step in range(budget):
        candidates=[]; best_key=None; best=None
        for pid in sorted(set(pool)-set(chosen)):
            panel=chosen+[pid]; cols=features.columns(panel)
            model=RandomForestClassifier(n_estimators=estimators,random_state=seed,class_weight='balanced',min_samples_leaf=min_samples_leaf,max_depth=max_depth,n_jobs=1)
            model.fit(x[cols],y); pred=model.predict(v[cols]); m=metrics(vy,pred,labels)
            candidates.append({'added_probe':pid,'panel':panel,'accuracy':m['accuracy'],'macro_f1':m['macro_f1']})
            key=(m['accuracy'],m['macro_f1'])
            if best_key is None or key>best_key:
                best_key=key;best=(pid,model,m)
        pid,winner,m=best;chosen.append(pid)
        rounds.append({'budget':step+1,'selected':list(chosen),'candidates':candidates,'validation':m})
    return chosen,winner,rounds


class RandomForestTrainer:
    def supports(self,info):return info.get('split_algorithm')==d.PANEL_ALGORITHM
    def run(self,ctx):
        import joblib, sklearn, pandas, numpy
        if ctx.split_algorithm!=d.PANEL_ALGORITHM:raise ValueError('RF trainer requires split-panel fixed probe protocol')
        params=ctx.parameters
        if set(params)-{'probe_budget','n_estimators','seed','min_samples_leaf','max_depth','prompt_definitions'}:
            raise ValueError('Unknown RF training parameter')
        pool=ctx.probe_pool; prompt_set=ctx.prompt_set_version
        defs=params.get('prompt_definitions')
        if not isinstance(defs,dict) or set(defs)!=set(pool) or not all(isinstance(t,str) and t.strip() for t in defs.values()):
            raise ValueError('Provide exact original prompt text for every pool ID')
        budget=params.get('probe_budget',len(pool)); estimators=params.get('n_estimators',100); seed=params.get('seed',42); leaf=params.get('min_samples_leaf',1); depth=params.get('max_depth')
        for value,lo,hi in [(budget,1,len(pool)),(estimators,1,2000),(seed,0,2**32-1),(leaf,1,100)]:
            if type(value) is not int or not lo<=value<=hi:raise ValueError('Invalid RF hyperparameter')
        if depth is not None and (type(depth) is not int or not 1<=depth<=100):raise ValueError('Invalid max_depth')
        train=load_traces(ctx.train_jsonl,pool,prompt_set); val=load_traces(ctx.validation_jsonl,pool,prompt_set)
        selected,model,rounds=fit_greedy(train,val,pool,budget=budget,estimators=estimators,seed=seed,min_samples_leaf=leaf,max_depth=depth)
        out=ctx.output_dir; labels=list(model.classes_)
        joblib.dump(model,out/'classifier.joblib',compress=3)
        shutil.copyfile(Path(features.__file__),out/'feature_extractor.py'); shutil.copyfile(Path(rf_features.__file__),out/'base_text_features.py')
        a.write_new(out/'feature_manifest.json',a.json_text({'feature_abi':features.FEATURE_ABI,'target':'model_key','feature_columns':features.columns(selected),'probes':[{'id':p,'text':defs[p]} for p in selected]}))
        a.write_new(out/'validation_report.json',a.json_text({'status':'exploratory_validation_not_test','algorithm':'greedy_forward_selection','objective':'accuracy_then_macro_f1_then_lexicographic_probe_id','candidate_pool':pool,'selected_panel':selected,'train_traces':len(train),'validation_traces':len(val),'train_personas':sorted({t['persona_id'] for t in train}),'validation_personas':sorted({t['persona_id'] for t in val}),'rounds':rounds,'test_used':False}))
        payloads=['classifier.joblib','feature_manifest.json','feature_extractor.py','base_text_features.py','validation_report.json']
        a.write_new(out/'manifest.json',a.json_text({'schema_version':'1.0','artifact_id':ctx.artifact_id,'adapter':'random_forest','stage':2,'kind':'sklearn_classifier','supported_models':labels,'required_files':[{'path':p,'sha256':a.digest(out/p)} for p in payloads],
            'options':{'feature_abi':features.FEATURE_ABI,'label_order':labels,'probe_ids':selected,'sklearn_version':sklearn.__version__,'acceptance_policy':{'mode':'review_only'},'input_policy':'fixed_probe_text_only','n_estimators':estimators,'random_state':seed,'min_samples_leaf':leaf,'max_depth':depth},
            'provenance':{'source':'LLMmap-inspired RF trainer, existing stylometric features plus hashed lexical features','training_code_revision':'sha256:'+a.digest(Path(__file__)),'runtime_dependencies':{'python':sys.version.split()[0],'scikit-learn':sklearn.__version__,'joblib':joblib.__version__,'pandas':pandas.__version__,'numpy':numpy.__version__},'training_dataset_id':ctx.dataset_id,'split_id':ctx.split_id,'dataset_manifest_sha256':ctx.dataset_manifest_sha256,'split_manifest_sha256':ctx.split_manifest_sha256,'eligibility_policy':ctx.eligibility_policy,'training_traces':len(train),'validation_traces':len(val),'test_used':False}}))
