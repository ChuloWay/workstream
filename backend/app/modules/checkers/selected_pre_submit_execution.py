"""Selected default-plus-external PRE execution over one ART callback."""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from app.core.cancellation import await_cancellation_resistant
from app.interfaces.artifacts import ArtifactScratchIntegrityError
from app.interfaces.external_checker_execution import ExternalCheckerExecutionAdapter
from app.interfaces.external_services import (
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)
from app.modules.checkers.api.default_checker import WorkstreamDefaultCheckerInput
from app.modules.checkers.api.external import (
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
    external_checker_json_hash,
    make_external_checker_execution_request,
)
from app.modules.checkers.api.external_policy import LockedExternalPreSubmitPolicy
from app.modules.checkers.api.materialization import SubmissionMaterialEntry
from app.modules.checkers.api.selected_pre_submit import (
    ExternalPreSubmitIsolationFacts,
    ExternalPreSubmitMemberFacts,
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitInfrastructureUnavailable,
)
from app.modules.checkers.default_checker import (
    WorkstreamDefaultCheckerUnavailable,
    evaluate_verified_archive,
)


class _PreSubmitMaterialView:
    """Keep verified reads and the opaque PRE grant inside one ART callback."""

    def __init__(self, tree, *, grants, workspace) -> None:
        self._tree, self._grants, self._workspace = tree, grants, workspace
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("pre-submit material view is closed")

    @property
    def entries(self) -> tuple[SubmissionMaterialEntry, ...]:
        self._require_open()
        return tuple(
            SubmissionMaterialEntry(
                item.normalized_path,
                item.entry_type.value,
                item.byte_count,
                item.sha256,
                item.executable,
            )
            for item in self._tree.entries
        )

    def read_file(self, normalized_path: str, *, maximum_bytes: int) -> bytes:
        self._require_open()
        return self._tree.read_file(normalized_path, maximum_bytes=maximum_bytes)

    def external_checker_grant(self, request):
        self._require_open()
        return self._grants.issue(request, self._workspace)


def _input_body(
    *,
    requirement_id: str,
    identity: PreSubmitExternalCheckerIdentity,
    material: PreSubmitExternalCheckerMaterial,
    value: WorkstreamDefaultCheckerInput,
) -> dict[str, object]:
    """Build the one normalized public PRE image input from verified facts."""
    return {
        "schema_version": "workstream.external_checker_pre_submit_input.v1",
        "requirement_id": requirement_id,
        "project_id": str(identity.project_id),
        "task_id": str(identity.task_id),
        "assignment_id": str(identity.assignment_id),
        "archive_sha256": material.archive_sha256,
        "archive_byte_count": material.archive_byte_count,
        "semantic_manifest_sha256": material.semantic_manifest_sha256,
        "manifest": [asdict(item) for item in value.entries],
        "packet": {
            "summary": value.packet.summary,
            "contributor_attestation": value.packet.contributor_attestation,
        },
    }


class SelectedPreSubmitProcessor:
    """Run the default and every required locked external PRE image in order."""

    def __init__(
        self,
        *,
        archive_inspector,
        inspection,
        policy: LockedExternalPreSubmitPolicy,
        default_input: WorkstreamDefaultCheckerInput,
        identity: PreSubmitExternalCheckerIdentity,
        material: PreSubmitExternalCheckerMaterial,
        grants,
        execution: ExternalCheckerExecutionAdapter,
    ) -> None:
        self._inspector, self._inspection = archive_inspector, inspection
        self._policy, self._default_input = policy, default_input
        self._identity, self._material = identity, material
        self._grants, self._execution = grants, execution
        self._aborted = False
        self._active: asyncio.Task | None = None
        self._view: _PreSubmitMaterialView | None = None

    def abort(self) -> None:
        """Revoke callback access and cancel the active default/image invocation."""
        self._aborted = True
        if self._view is not None:
            self._view.close()
        if self._active is not None:
            self._active.cancel()

    async def process(self, reader, workspace) -> SelectedPreSubmitExecutionFacts:
        """Project once, execute outside DB, and drain ART cleanup before return."""
        projection = self._inspector._projected_tree(
            reader, workspace, expected=self._inspection
        )
        tree = await asyncio.to_thread(projection.__enter__)
        try:
            if self._aborted:
                raise asyncio.CancelledError
            self._view = _PreSubmitMaterialView(
                tree, grants=self._grants, workspace=workspace
            )
            self._active = asyncio.create_task(
                asyncio.to_thread(
                    evaluate_verified_archive, self._default_input, self._view
                )
            )
            default = await self._active
            members: list[ExternalPreSubmitMemberFacts] = []
            if default.eligible:
                for order, binding in enumerate(self._policy.entries):
                    if self._aborted:
                        raise asyncio.CancelledError
                    input_value = _input_body(
                        requirement_id=binding.requirement_id,
                        identity=self._identity,
                        material=self._material,
                        value=self._default_input,
                    )
                    request = make_external_checker_execution_request(
                        registry=binding.registry,
                        identity=self._identity,
                        configuration=binding.configuration,
                        configuration_sha256=binding.configuration_sha256,
                        input=input_value,
                        input_sha256=external_checker_json_hash(input_value),
                        materials=(self._material,),
                    )
                    with self._view.external_checker_grant(request) as grant:
                        self._active = asyncio.create_task(
                            self._execution.execute(request, grant)
                        )
                        response = await self._active
                    result = response.result
                    if result.outcome == "infrastructure_failed":
                        raise SelectedPreSubmitInfrastructureUnavailable(
                            result.infrastructure_failure_code or "invalid_output"
                        )
                    if response.isolation is None:
                        raise SelectedPreSubmitInfrastructureUnavailable("invalid_output")
                    member = ExternalPreSubmitMemberFacts(
                        order=order,
                        requirement_id=binding.requirement_id,
                        registry_entry_id=binding.registry.registry_entry_id,
                        registry_entry_digest=binding.registry.entry_digest,
                        request_digest=request.request_digest,
                        result=result,
                        isolation=ExternalPreSubmitIsolationFacts(
                            **asdict(response.isolation)
                        ),
                    )
                    members.append(member)
                    if result.verdict == "failed":
                        break
            eligible = default.eligible and len(members) == len(self._policy.entries) and all(
                item.result.verdict == "passed" for item in members
            )
            return SelectedPreSubmitExecutionFacts(
                policy_sha256=self._policy.policy_sha256,
                workstream_default=default,
                required_external_count=len(self._policy.entries),
                external_members=tuple(members),
                eligible=eligible,
            )
        except WorkstreamDefaultCheckerUnavailable as exc:
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable") from exc
        except ExternalServiceUnavailableError as exc:
            raise SelectedPreSubmitInfrastructureUnavailable(
                "implementation_unavailable"
            ) from exc
        except ExternalServiceProtocolError as exc:
            raise SelectedPreSubmitInfrastructureUnavailable("invalid_output") from exc
        finally:
            if self._view is not None:
                self._view.close()
            self._active = None
            try:
                await await_cancellation_resistant(
                    asyncio.to_thread(projection.__exit__, None, None, None)
                )
            except ArtifactScratchIntegrityError:
                raise
            except Exception:
                raise ArtifactScratchIntegrityError(
                    "pre_submit_projection_cleanup_unconfirmed"
                ) from None


__all__ = ("SelectedPreSubmitProcessor",)
