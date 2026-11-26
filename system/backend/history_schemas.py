"""Pydantic contracts for M5 manual deployment history and published model cards."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class DeploymentCreate(StrictBody):
    label: str = Field(min_length=1, max_length=100)
    provider: Literal['openai'] = 'openai'  # M4 has one real target provider
    requested_model_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._:-]+$')

    @field_validator('label')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Label cannot be blank')
        return value.strip()


class ManualBaselineCreate(StrictBody):
    model_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._:-]+$')
    acknowledge_manual_review: Literal[True]
    review_note: str = Field(min_length=10, max_length=500)

    @field_validator('review_note')
    @classmethod
    def note_nonblank(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError('Provide at least ten characters describing review evidence')
        return value.strip()
