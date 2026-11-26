"""Notebook-derived LoRA trainer. No ML framework import or network access at plan time.

Balances each model/prompt cell on train and validation separately. This avoids
learning a model label from prompt availability. Only the orchestrator exports
are consumed; calibration/test are never passed to this trainer.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import math
import re
import shutil
import sys
from ..adapters.lora_preprocessing import BLANK_POLICY, prepare_response
from ..onboarding import artifacts as a, datasets as d

BASES = ('Qwen/Qwen2.5-1.5B','Qwen/Qwen2.5-0.5B')
TARGETS = ['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj']
DEFAULTS = dict(base_model=BASES[0], base_model_revision=None, max_tokens=512,
                lora_rank=32, lora_alpha=64, lora_dropout=.05, epochs=8,
                learning_rate=1e-4, weight_decay=.01, batch_size=2,
                gradient_accumulation_steps=8, max_train_per_class=200,
                seed=42, device='cuda', precision='fp16', model_ids=None,
                local_files_only=False)


def parameters(raw, *, require_revision=True):
    if set(raw)-set(DEFAULTS): raise ValueError('Unknown LoRA training parameter: '+str(sorted(set(raw)-set(DEFAULTS))))
    p={**DEFAULTS,**raw}
    if p['base_model'] not in BASES: raise ValueError('Use a supported Qwen2.5 base (0.5B or 1.5B)')
    rev=p['base_model_revision']
    if require_revision and (not isinstance(rev,str) or not re.fullmatch('[0-9a-f]{40}',rev)):
        raise ValueError('Supply base_model_revision: exact 40-character Hugging Face commit; never main')
    for key,lo,hi in [('max_tokens',8,8192),('lora_rank',1,128),('lora_alpha',1,512),('epochs',1,100),('batch_size',1,128),('gradient_accumulation_steps',1,256),('seed',0,2**32-1)]:
        if type(p[key]) is not int or not lo<=p[key]<=hi: raise ValueError('Invalid '+key)
    cap=p['max_train_per_class']
    if cap is not None and (type(cap) is not int or not 1<=cap<=1000000): raise ValueError('Invalid max_train_per_class')
    for key,lo,hi in [('lora_dropout',0,.99),('learning_rate',1e-8,1),('weight_decay',0,1)]:
        if type(p[key]) not in (int,float) or not math.isfinite(p[key]) or not lo<=p[key]<=hi: raise ValueError('Invalid '+key)
    if p['device'] not in ('cpu','cuda') or p['precision'] not in ('fp32','fp16','bf16') or (p['device']=='cpu' and p['precision']!='fp32'):
        raise ValueError('CPU requires fp32; CUDA supports fp32/fp16/bf16')
    if type(p['local_files_only']) is not bool: raise ValueError('local_files_only must be boolean')
    ids=p['model_ids']
    if ids is not None and (not isinstance(ids,list) or len(ids)<2 or any(not isinstance(x,str) or not x for x in ids) or len(ids)!=len(set(ids))):
        raise ValueError('model_ids must contain at least two unique canonical IDs')
    return p


def load_rows(path):
    out=[]; seen=set()
    for _,r,_ in d.read_rows(path):
        rid=r['record_id']
        if rid in seen or r.get('error') is not None: raise ValueError('Duplicate record or collection error in eligible export')
        seen.add(rid)
        text=prepare_response(r.get('response_text'),BLANK_POLICY)
        out.append({'id':rid,'model':r['model_key'],'prompt':(r['prompt_set_version'],r['prompt_id']),
                    'persona':r.get('persona_id'),'raw_text':r.get('response_text') or '', 'text':text,'blank':not (r.get('response_text') or '').strip()})
    return out


def _balance(rows, labels, seed, cap):
    cells=defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r['model'] in labels: cells[r['prompt']][r['model']].append(r)
    common=sorted(k for k,v in cells.items() if set(v)==set(labels))
    if not common: raise ValueError('No shared prompt/version across all selected models in this partition; collect a common panel or select compatible classes')
    if cap is not None and cap<len(common): raise ValueError('max_train_per_class must cover every shared prompt; increase cap or set null')
    # Equal quotas per label for every retained prompt; deterministic round-robin cap.
    quota={k:0 for k in common}; sizes={k:min(len(cells[k][m]) for m in labels) for k in common}
    left=sum(sizes.values()) if cap is None else min(cap,sum(sizes.values()))
    while left:
        for k in common:
            if quota[k]<sizes[k] and left: quota[k]+=1; left-=1
    def rank(r): return hashlib.sha256(f'{seed}\0{r["id"]}'.encode()).digest()
    selected=[r for k in common for m in labels for r in sorted(cells[k][m],key=rank)[:quota[k]]]
    selected.sort(key=rank)
    return selected, {'source_rows':len(rows),'selected_model_rows':sum(r['model'] in labels for r in rows),
                      'retained_rows':len(selected),'blank_rows':sum(r['blank'] for r in selected),
                      'class_counts':dict(Counter(r['model'] for r in selected)),
                      'shared_prompts':[list(k) for k in common],
                      'dropped_rows':len(rows)-len(selected),'samples_per_class_by_prompt':[{'prompt':list(k),'count':quota[k]} for k in common]}


def prepare_data(train_path, validation_path, p, algorithm):
    train, val=load_rows(train_path),load_rows(validation_path)
    labels=sorted(p['model_ids'] or {r['model'] for r in train})
    if len(labels)<2 or not set(labels)<={r['model'] for r in train} or not set(labels)<={r['model'] for r in val}:
        raise ValueError('At least two selected labels must occur in both train and validation')
    if p['model_ids'] is None and {r['model'] for r in val}!=set(labels): raise ValueError('Training and validation class sets differ; choose model_ids explicitly')
    if {r['id'] for r in train}&{r['id'] for r in val}: raise ValueError('Record leakage between train and validation')
    if algorithm==d.PANEL_ALGORITHM:
        if {r['persona'] for r in train}&{r['persona'] for r in val}: raise ValueError('Persona leakage between train and validation')
    elif algorithm==d.ALGORITHM:
        if {r['prompt'][1] for r in train}&{r['prompt'][1] for r in val}: raise ValueError('Prompt leakage between train and validation')
    else: raise ValueError('Unsupported split protocol')
    train,tr=_balance(train,labels,p['seed'],p['max_train_per_class'])
    val,vr=_balance(val,labels,p['seed'],None)
    if algorithm==d.PANEL_ALGORITHM and tr['shared_prompts']!=vr['shared_prompts']: raise ValueError('Fixed-panel shared prompts differ across partitions')
    return train,val,labels,{'labels':labels,'train':tr,'validation':vr,'split_algorithm':algorithm,
                              'input_policy':BLANK_POLICY,'test_used':False,'balanced_per_prompt':True}


def metrics(y,pred,labels):
    from sklearn.metrics import accuracy_score,f1_score,classification_report,confusion_matrix
    return {'accuracy':float(accuracy_score(y,pred)), 'macro_f1':float(f1_score(y,pred,labels=labels,average='macro',zero_division=0)),
            'classification_report':classification_report(y,pred,labels=labels,output_dict=True,zero_division=0),
            'confusion_matrix':confusion_matrix(y,pred,labels=labels).tolist(),'label_order':labels}


def fit_export(ctx,p,train,val,labels):
    """Actual HF/PEFT execution. Imported only when a developer requests training."""
    try:
        import torch, transformers, peft, accelerate, safetensors, sklearn, numpy as np
        from transformers import AutoTokenizer,AutoModelForSequenceClassification,DataCollatorWithPadding,Trainer,TrainingArguments,set_seed
        from peft import LoraConfig,TaskType,get_peft_model
        from safetensors import safe_open
    except ImportError as exc:
        raise RuntimeError('Install requirements-lora-training.txt in a separate training environment') from exc
    if p['device']=='cuda' and not torch.cuda.is_available(): raise RuntimeError('CUDA requested but unavailable; use a GPU or explicit CPU/fp32 smoke configuration')
    if p['precision']=='bf16' and not torch.cuda.is_bf16_supported(): raise RuntimeError('GPU does not support bf16')
    set_seed(p['seed']); id2label=dict(enumerate(labels)); label2id={v:k for k,v in id2label.items()}
    base_kwargs=dict(revision=p['base_model_revision'],local_files_only=p['local_files_only'],trust_remote_code=False)
    tok=AutoTokenizer.from_pretrained(p['base_model'],**base_kwargs)
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    if tok.pad_token_id is None: raise ValueError('Base tokenizer needs a padding token')
    tok.padding_side='right'
    base=AutoModelForSequenceClassification.from_pretrained(p['base_model'],num_labels=len(labels),id2label=id2label,label2id=label2id,**base_kwargs).float()
    base.config.pad_token_id=tok.pad_token_id
    model=get_peft_model(base,LoraConfig(task_type=TaskType.SEQ_CLS,r=p['lora_rank'],lora_alpha=p['lora_alpha'],lora_dropout=p['lora_dropout'],target_modules=TARGETS,modules_to_save=['score'],revision=p['base_model_revision']))
    def encode(rows):
        items=[]
        for r in rows:
            enc=tok(r['text'],truncation=True,max_length=p['max_tokens'])
            if not enc['input_ids']: raise ValueError('Tokenizer emitted no tokens')
            enc['labels']=label2id[r['model']];items.append(enc)
        return items
    train_ds,val_ds=encode(train),encode(val)
    work=ctx.output_dir.parent/'hf_work'
    args=TrainingArguments(output_dir=str(work/'trainer'),per_device_train_batch_size=p['batch_size'],per_device_eval_batch_size=p['batch_size'],gradient_accumulation_steps=p['gradient_accumulation_steps'],num_train_epochs=p['epochs'],learning_rate=p['learning_rate'],weight_decay=p['weight_decay'],fp16=p['precision']=='fp16',bf16=p['precision']=='bf16',use_cpu=p['device']=='cpu',logging_steps=10,save_strategy='no',report_to=[],seed=p['seed'],data_seed=p['seed'],disable_tqdm=True,remove_unused_columns=False,label_names=['labels'])
    trainer=Trainer(model=model,args=args,train_dataset=train_ds,data_collator=DataCollatorWithPadding(tokenizer=tok))
    trainer.train(); result=trainer.predict(val_ds); logits=result.predictions[0] if isinstance(result.predictions,tuple) else result.predictions
    logits=np.asarray(logits); expected=(len(val),len(labels))
    if logits.shape!=expected or not np.isfinite(logits).all(): raise ValueError('Invalid validation logits')
    pred=[labels[i] for i in logits.argmax(axis=1)]; truth=[r['model'] for r in val]
    # Copy only inference payloads; Trainer checkpoints and README are not required.
    saved=work/'adapter';model.save_pretrained(str(saved),safe_serialization=True)
    for name in ('adapter_model.safetensors','adapter_config.json'): shutil.copyfile(saved/name,ctx.output_dir/name)
    shutil.rmtree(saved)
    with safe_open(ctx.output_dir/'adapter_model.safetensors',framework='numpy',device='cpu') as f:
        heads=[k for k in f.keys() if k.endswith('score.weight')]
        if len(heads)!=1: raise ValueError('Expected one saved classification head')
        shape=list(f.get_slice(heads[0]).get_shape())
        if len(shape)!=2 or shape[0]!=len(labels): raise ValueError('Saved classification head mismatch')
    dependencies={'python':sys.version.split()[0],'torch':torch.__version__,'transformers':transformers.__version__,'peft':peft.__version__,'accelerate':accelerate.__version__,'safetensors':safetensors.__version__,'scikit-learn':sklearn.__version__,'numpy':np.__version__}
    return shape,metrics(truth,pred,labels),dependencies


class LoRATrainer:
    def supports(self,info): return info.get('split_algorithm') in (d.ALGORITHM,d.PANEL_ALGORITHM)
    def check_parameters(self,raw): parameters(raw)
    def run(self,ctx):
        p=parameters(ctx.parameters)
        train,val,labels,report=prepare_data(ctx.train_jsonl,ctx.validation_jsonl,p,ctx.split_algorithm)
        a.write_new(ctx.output_dir/'data_report.json',a.json_text(report))
        shape,validation,deps=fit_export(ctx,p,train,val,labels)
        out=ctx.output_dir
        a.write_new(out/'validation_report.json',a.json_text({'status':'exploratory_validation_not_test','test_used':False,'metrics':validation,'runtime_reload_validated':False,'input':'single_response_only'}))
        files=['adapter_config.json','adapter_model.safetensors','data_report.json','validation_report.json']
        a.write_new(out/'manifest.json',a.json_text({'schema_version':'1.0','artifact_id':ctx.artifact_id,'adapter':'lora','stage':2,'kind':'peft_adapter','supported_models':labels,
            'required_files':[{'path':f,'sha256':a.digest(out/f)} for f in files],
            'options':{'base_model':p['base_model'],'base_model_revision':p['base_model_revision'],'max_tokens':p['max_tokens'],'label_order':labels,'label_order_status':'confirmed','classifier_head_shape':shape,'lora_rank':p['lora_rank'],'lora_alpha':p['lora_alpha'],'input_policy':BLANK_POLICY,'acceptance_policy':{'mode':'review_only'}},
            'provenance':{'source':'Notebook v2_lora_finetuning.ipynb, adapted to shared prompt balancing and orchestrator splits','training_code_revision':'sha256:'+a.digest(Path(__file__)),'runtime_dependencies':deps,'training_dataset_id':ctx.dataset_id,'split_id':ctx.split_id,'dataset_manifest_sha256':ctx.dataset_manifest_sha256,'split_manifest_sha256':ctx.split_manifest_sha256,'eligibility_policy':ctx.eligibility_policy,'label_order_evidence':'Sorted canonical labels used directly for training label2id/id2label and saved score head; see data_report.json','training_parameters':p,'input_preprocessing_sha256':a.digest(Path(__file__).parents[1]/'adapters/lora_preprocessing.py'),'test_used':False,'runtime_reload_validated':False}}))
