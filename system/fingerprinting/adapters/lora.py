"""Stage 2 PEFT sequence-classifier adapter for the LoRA notebook's five-class model.

The model's identity prediction and the *decision to accept* it are separate.
This adapter defaults to review_only, since a closed-set softmax is not an
open-set confidence measurement. No Hugging Face model is loaded on import.

The optional predictor callable is ONLY for isolated tests; real Factory
construction always loads the signed-off PEFT bundle after readiness checks.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from time import perf_counter

from ..config import Stage2MethodSelection
from ..registry import ArtifactManifest
from ..schemas import IdentificationInput, IdentificationResult, ProbeQuestion


class LoRAConfigurationError(ValueError):
    pass


# Return one probability per class, in the declared order.
PredictionFunction = Callable[[str], Sequence[float]]


class LoRAIdentifier:
    name = 'lora'

    def __init__(self, manifest: ArtifactManifest, *, predictor: PredictionFunction | None = None):
        if manifest.adapter != 'lora' or manifest.stage != 2:
            raise LoRAConfigurationError('LoRA requires a Stage 2 lora manifest')
        self.manifest = manifest
        self.artifact_id = manifest.artifact_id
        opts = manifest.options
        labels = opts.get('label_order')
        if (not isinstance(labels, list) or not labels or
                len(labels) != len(set(labels)) or
                any(not isinstance(x, str) or not x for x in labels)):
            raise LoRAConfigurationError('Manifest must declare a unique nonempty label_order')
        if set(labels) != set(manifest.supported_models):
            raise LoRAConfigurationError('Manifest label_order and supported_models disagree')
        self.labels = tuple(labels)
        if not isinstance(opts.get('base_model'), str) or not opts['base_model'].strip():
            raise LoRAConfigurationError('Manifest must include a nonempty base_model')
        self.base_revision = opts.get('base_model_revision')
        self.max_tokens = opts.get('max_tokens')
        if not isinstance(self.max_tokens, int) or not (0 < self.max_tokens <= 8192):
            raise LoRAConfigurationError('max_tokens must be a positive integer')
        policy = opts.get('acceptance_policy', {'mode': 'review_only'})
        if not isinstance(policy, dict):
            raise LoRAConfigurationError('acceptance_policy must be an object')
        mode = policy.get('mode')
        if mode not in ('review_only', 'validated_threshold'):
            raise LoRAConfigurationError('Unknown LoRA acceptance policy')
        self.threshold = None
        if mode == 'validated_threshold':
            t = policy.get('threshold')
            if (isinstance(t, bool) or not isinstance(t, (int, float)) or
                    not math.isfinite(t) or not (0.0 < t <= 1.0)):
                raise LoRAConfigurationError('validated_threshold requires threshold in (0,1]')
            if not isinstance(policy.get('validation_id'), str) or not policy['validation_id'].strip():
                raise LoRAConfigurationError('validated_threshold requires validation_id')
            if policy.get('includes_unknown_models') is not True:
                raise LoRAConfigurationError('validated_threshold must be tested on unknown-model cases')
            self.threshold = float(t)
        self.acceptance_policy = mode
        self._predictor = predictor
        self._loaded = predictor is not None

    def required_probes(self) -> Sequence[ProbeQuestion]:
        return ()

    def _load_predictor(self) -> PredictionFunction:
        """Lazy, one-time load; only called after Factory checks the artifact.

        For a reproducible release, pin base_model_revision in the manifest.
        An adapter without a saved sequence-classification head is rejected.
        """
        if not self.base_revision:
            raise LoRAConfigurationError('Pin options.base_model_revision to a Hugging Face commit before real inference')
        root = self.manifest.directory
        # A direct adapter invocation cannot bypass checksum verification. The
        # factory also performs this check before building the pipeline.
        for item in self.manifest.required_files:
            file_path = root / item.relative_path
            if not file_path.is_file():
                raise FileNotFoundError(f'Missing LoRA artifact: {item.relative_path}')
            if not item.sha256:
                raise LoRAConfigurationError(f'Unchecksummed LoRA artifact: {item.relative_path}')
            with file_path.open('rb') as f:
                if hashlib.file_digest(f, 'sha256').hexdigest() != item.sha256:
                    raise LoRAConfigurationError(f'LoRA checksum mismatch: {item.relative_path}')
        cfg_path = root / 'adapter_config.json' 
        weights_path = root / 'adapter_model.safetensors'
        if not cfg_path.is_file() or not weights_path.is_file():
            raise FileNotFoundError('LoRA trained adapter files are not available; obtain my_lora_adapter.zip')
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        if cfg.get('task_type') != 'SEQ_CLS':
            raise LoRAConfigurationError('Expected PEFT task_type=SEQ_CLS')
        if cfg.get('base_model_name_or_path') not in (None, self.manifest.options['base_model']):
            raise LoRAConfigurationError('Adapter base_model_name_or_path does not match manifest')
        for key, cfg_key in (('lora_rank', 'r'), ('lora_alpha', 'lora_alpha')):
            expected_value = self.manifest.options.get(key)
            if expected_value is not None and cfg.get(cfg_key) != expected_value:
                raise LoRAConfigurationError(f'Adapter {cfg_key} does not match {key} in manifest')

        try:
            from safetensors import safe_open
        except ImportError as exc:
            raise RuntimeError('Install requirements-lora.txt (safetensors)') from exc
        with safe_open(weights_path, framework='pt', device='cpu') as f:
            keys = list(f.keys())
            expected_shape = self.manifest.options.get('classifier_head_shape')
            if expected_shape is not None:
                matching = [name for name in keys if name.endswith('score.weight')]
                if len(matching) != 1 or list(f.get_slice(matching[0]).get_shape()) != expected_shape:
                    raise LoRAConfigurationError('Trained classification head shape does not match manifest')
        # Qwen2.5ForSequenceClassification has a trained ``score`` head.
        # A PEFT bundle missing it would silently use a randomly initialized head.
        if not any('.score.' in key or key.startswith('score.') for key in keys):
            raise LoRAConfigurationError('LoRA adapter does not include a trained sequence-classification head')

        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError('Install requirements-lora.txt (torch, peft, transformers)') from exc

        base_name = self.manifest.options['base_model']
        labels = list(self.labels)
        id2label = dict(enumerate(labels))
        label2id = {v: k for k, v in id2label.items()}
        tok = AutoTokenizer.from_pretrained(base_name, revision=self.base_revision)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        tok.padding_side = 'right'
        base = AutoModelForSequenceClassification.from_pretrained(
            base_name, revision=self.base_revision,
            num_labels=len(labels), id2label=id2label, label2id=label2id)
        base.config.pad_token_id = tok.pad_token_id
        model = PeftModel.from_pretrained(base, str(root), is_trainable=False)
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model.to(device)
        model.eval()

        def run(text: str) -> Sequence[float]:
            encoded = tok(text.strip(), truncation=True, max_length=self.max_tokens,
                          return_tensors='pt').to(device)
            with torch.inference_mode():
                scores = torch.softmax(model(**encoded).logits.float(), dim=-1)[0]
            return scores.detach().cpu().tolist()
        return run

    def identify(self, context: IdentificationInput) -> IdentificationResult:
        start = perf_counter()
        if not self._loaded:
            self._predictor = self._load_predictor()
            self._loaded = True
        raw = list(self._predictor(context.initial.response_text))
        if len(raw) != len(self.labels):
            raise ValueError(f'LoRA returned {len(raw)} scores; expected {len(self.labels)}')
        if (any(isinstance(x, bool) or not isinstance(x, (int, float)) or
                not math.isfinite(x) or not (0 <= x <= 1) for x in raw)
                or abs(sum(raw) - 1) > 1e-3):
            raise ValueError('LoRA predictor must return finite normalized class probabilities')
        ix = max(range(len(raw)), key=lambda i: raw[i])
        # The supplied 0.5B checkpoint has no trustworthy saved class-ID mapping.
        # Do not expose model names or accepted identities from provisional labels.
        mapping_unconfirmed = (self.manifest.options.get('label_order_status') == 'provisional_unconfirmed')
        candidate = None if mapping_unconfirmed else self.labels[ix]
        maximum = float(raw[ix])
        accepted = (not mapping_unconfirmed and self.threshold is not None
                    and maximum >= self.threshold)
        return IdentificationResult(
            method='lora', outcome='identified' if accepted else 'unknown',
            candidate_model_id=candidate, accepted_model_id=candidate if accepted else None,
            score=maximum, score_type='max_softmax', handoff_requested=not accepted,
            model_scores=({} if mapping_unconfirmed else
                          {label: float(score) for label, score in zip(self.labels, raw)}),
            reason=('Checkpoint class-to-model mapping is not yet validated; raw class scores only'
                    if mapping_unconfirmed else
                    'Validated threshold accepted candidate' if accepted else
                    'Closed-set prediction not accepted; continue to next identifier'),
            duration_ms=(perf_counter() - start) * 1000,
            diagnostics={'artifact_id': self.artifact_id,
                         'acceptance_policy': self.acceptance_policy,
                         'acceptance_threshold': self.threshold,
                         'closed_set': True, 'input': 'initial_response_only',
                         'label_order': (None if mapping_unconfirmed else list(self.labels)),
                         'label_order_status': self.manifest.options.get('label_order_status', 'declared'),
                         'raw_class_probabilities': (list(raw) if mapping_unconfirmed else None)})


def build_lora(manifest: ArtifactManifest, selection: Stage2MethodSelection) -> LoRAIdentifier:
    if selection.adapter != 'lora' or selection.artifact_id != manifest.artifact_id:
        raise LoRAConfigurationError('LoRA builder selection does not match artifact')
    # The Factory's readiness check must have passed prior to building for production.
    # Do NOT use this constructor with require_ready=False and real inference.
    return LoRAIdentifier(manifest)
