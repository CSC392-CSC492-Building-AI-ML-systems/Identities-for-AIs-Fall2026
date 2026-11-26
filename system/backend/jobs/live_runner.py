"""Worker that executes a live target request with a short-lived decrypted key.

Legacy jobs use a mock judge; Stage 2 jobs are review-only with explicit external judge consent.
"""
from __future__ import annotations

from uuid import uuid4

from ..providers.openai import ProviderRequestError
from ..ui_results import summarize_unvalidated_live_result, summarize_stage2_result
from ..schemas import LiveOpenAIAnalyzeResponse
from ..security.crypto import FileSecretVault
from ..services.live import LiveOpenAIAnalysisGateway
from .live_store import SqliteLiveJobStore


class LiveJobWorker:
    def __init__(self, store: SqliteLiveJobStore, vault: FileSecretVault,
                 gateway: LiveOpenAIAnalysisGateway, *, worker_id: str | None=None,
                 mode: str = "live_target_mock_judge", live_judge_gateway=None):
        self.store=store
        self.vault=vault
        self.gateway=gateway
        self.mode=mode
        self.live_judge_gateway=live_judge_gateway
        if mode not in ("live_target_mock_judge", "live_stage2_review"):
            raise ValueError("Invalid worker mode")
        self.worker_id=worker_id or f'live-worker-{uuid4()}'

    def run_once(self) -> str | None:
        for expired in self.store.expire_queued() + self.store.expire_abandoned_running():
            self.vault.delete(expired)
        claimed=self.store.claim_next(self.worker_id, mode=self.mode)
        if claimed is None:
            return None
        job_id,owner_id,request=claimed
        try:
            gateway=self.gateway
            if request.get('allow_live_judge') is True:
                if self.mode != 'live_stage2_review' or self.live_judge_gateway is None:
                    self.store.finish(job_id,self.worker_id,error_code='JUDGE_NOT_CONFIGURED')
                    return job_id
                gateway=self.live_judge_gateway
            key=self.vault.read(job_id,owner_id)
            try:
                report=gateway.analyze(
                    request['prompt_text'],api_key=key,target_model=request['target_model'],use_stage1=False)
            finally:
                key=None
            fingerprint=report.fingerprint
            if self.mode == 'live_stage2_review':
                view=summarize_stage2_result(report,request.get('baseline'),gateway.workflow.catalog,gateway.judge)
                # Never expose arbitrary exception messages or judge-authored text.
                # No accepted identity is returned even if an adapter regresses.
                status='error' if fingerprint.final.status == 'error' else 'needs_review'
                result=LiveOpenAIAnalyzeResponse(
                    mode=self.mode, request_id=report.request_id,status=status,model_id=None,
                    stage1_enabled=False,model_card_status='unconfirmed',
                    change_status='unresolved' if request.get('baseline') else 'no_baseline',
                    target_queries=report.target_queries,
                    report={'config_sha256':fingerprint.config_sha256,
                            'artifact_ids':{k:v for k,v in fingerprint.artifact_ids.items() if k != 'stage1'},
                            'method_candidates':view['method_candidates']},ui_result=view,
                ).model_dump(mode='json')
                self.store.finish(job_id,self.worker_id,result=result)
                return job_id
            result=LiveOpenAIAnalyzeResponse(
                request_id=report.request_id,status=fingerprint.final.status,
                model_id=fingerprint.final.model_id,stage1_enabled=fingerprint.stage1_enabled,
                model_card_status=report.model_card_status,change_status=report.change_status,
                target_queries=report.target_queries,report=report.to_dict(),
                ui_result=summarize_unvalidated_live_result(request.get('baseline')),
            ).model_dump(mode='json')
            self.store.finish(job_id,self.worker_id,result=result)
        except ProviderRequestError:
            self.store.finish(job_id,self.worker_id,error_code='PROVIDER_ERROR')
        except (FileNotFoundError,ValueError):
            self.store.finish(job_id,self.worker_id,error_code='CREDENTIAL_UNAVAILABLE')
        except Exception:
            # Never store exception messages: HTTP SDK errors may include secrets.
            self.store.finish(job_id,self.worker_id,error_code='ANALYSIS_FAILED')
        finally:
            # Retire the credential after success/failure; encrypted file deletion
            # is not a guarantee of secure erasure on SSDs, backups or snapshots.
            self.vault.delete(job_id)
        return job_id
