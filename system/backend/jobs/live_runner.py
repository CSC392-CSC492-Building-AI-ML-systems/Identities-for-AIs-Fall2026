"""Worker that executes a live target request with a short-lived decrypted key.

The judge remains MOCKED: results must never assert verified identity.
"""
from __future__ import annotations

from uuid import uuid4

from ..providers.openai import ProviderRequestError
from ..ui_results import summarize_unvalidated_live_result
from ..schemas import LiveOpenAIAnalyzeResponse
from ..security.crypto import FileSecretVault
from ..services.live import LiveOpenAIAnalysisGateway
from .live_store import SqliteLiveJobStore


class LiveJobWorker:
    def __init__(self, store: SqliteLiveJobStore, vault: FileSecretVault,
                 gateway: LiveOpenAIAnalysisGateway, *, worker_id: str | None=None):
        self.store=store
        self.vault=vault
        self.gateway=gateway
        self.worker_id=worker_id or f'live-worker-{uuid4()}'

    def run_once(self) -> str | None:
        for expired in self.store.expire_queued() + self.store.expire_abandoned_running():
            self.vault.delete(expired)
        claimed=self.store.claim_next(self.worker_id)
        if claimed is None:
            return None
        job_id,owner_id,request=claimed
        try:
            key=self.vault.read(job_id,owner_id)
            try:
                report=self.gateway.analyze(
                    request['prompt_text'],api_key=key,target_model=request['target_model'],use_stage1=False)
            finally:
                key=None
            fingerprint=report.fingerprint
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
