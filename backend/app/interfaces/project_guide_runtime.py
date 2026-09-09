"""Immutable, credential-free execution configuration for a guide attempt."""

from __future__ import annotations

import hashlib
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.core.hashing import canonical_json_hash
from app.interfaces.external_services import ExternalServiceAdapterIdentity


class ProjectGuideRuntimeConfiguration(BaseModel):
    """Exact trusted configuration captured before authorizing an attempt.

    Instructions are operator-authored evidence, never interpolated secrets or
    project material. Credentials remain with the selected provider adapter.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_key: Literal["project_guide_compilation"] = "project_guide_compilation"
    runtime_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    model_provider: Literal["openai", "openai_compatible"]
    model: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")
    model_api: Literal["responses", "chat_completions"]
    model_endpoint: str | None = Field(default=None, max_length=500)
    instruction_id: Literal["project_guide_compilation"] = "project_guide_compilation"
    instruction_version: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=16_000)
    instructions_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    timeout_seconds: StrictInt = Field(ge=1, le=7200)
    maximum_prompt_bytes: StrictInt = Field(ge=1024, le=16 * 1024 * 1024)

    @field_validator("model_endpoint")
    @classmethod
    def validate_endpoint(cls, value: str | None) -> str | None:
        """Allow only a trusted HTTPS base endpoint without secret URL parts."""
        if value is not None:
            parsed = urlsplit(value)
            if (
                re.fullmatch(r"https://[a-zA-Z0-9.-]+(:[0-9]{1,5})?(/[^?#@\s]*)?", value) is None
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or any(character.isspace() for character in value)
            ):
                raise ValueError("model endpoint must be a credential-free HTTPS base URL")
        return value

    @model_validator(mode="after")
    def validate_snapshot(self) -> ProjectGuideRuntimeConfiguration:
        """Bind exact instruction bytes and require an explicit provider endpoint."""
        if (
            self.instructions_sha256
            != "sha256:" + hashlib.sha256(self.instructions.encode("utf-8")).hexdigest()
        ):
            raise ValueError("project guide instruction hash mismatch")
        if (self.model_provider == "openai_compatible") != (self.model_endpoint is not None):
            raise ValueError("model provider and endpoint do not match")
        return self

    @property
    def adapter_identity(self) -> ExternalServiceAdapterIdentity:
        """Return the exact shared-factory identity selected by this attempt."""
        return ExternalServiceAdapterIdentity(self.capability_key, self.runtime_key)

    @property
    def sha256(self) -> str:
        """Hash the complete closed configuration, including exact instructions."""
        return canonical_json_hash(self.model_dump(mode="json"))
