"""Rollback-only real-state guard probe; never an authorization or mutation API."""

from __future__ import annotations

import argparse
import ast
import asyncio
import inspect
import json
from pathlib import Path
import textwrap
from uuid import UUID

from external_api_drill import ProbeFailure, isolation

FAILURE_CODES = frozenset({
    "isolation_required", "fresh_owned_database_required", "mutation_target_not_unique",
    "unexpected_effective_count", "missing_target", "target_fact_mismatch", "missing_link",
})


def boundary_mutant(function):
    """Change exactly one owned <=1 comparator; execute only in this subprocess."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    candidates = [node for node in ast.walk(tree) if isinstance(node, ast.Compare)
                  and len(node.ops) == 1 and isinstance(node.ops[0], ast.LtE)
                  and len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)
                  and type(node.comparators[0].value) is int and node.comparators[0].value == 1]
    if len(candidates) != 1:
        raise ValueError("mutation_target_not_unique")
    candidates[0].ops[0] = ast.Lt()
    namespace = function.__globals__.copy()
    exec(compile(ast.fix_missing_locations(tree), "<isolated-guard-mutant>", "exec"), namespace)
    return namespace[function.__name__]


async def probe(args):
    await isolation(args.isolation_metadata, require_empty=False)
    from sqlalchemy import text
    from app.db.session import dispose_engine, get_session_factory
    from app.modules.authorization.admin_service import AdminRoleGrantService
    from app.modules.authorization.lifecycle_service import ActorLifecycleService, IdentityLinkLifecycleService
    from app.modules.authorization.repository import AdminAuthorizationRepository
    from app.modules.authorization.schemas import (
        ActorProfileSuspendRequest, ActorProfileDeactivateRequest, ActorIdentityLinkRevokeRequest,
        AuthorityOperation, derive_reason_digest,
    )

    owners = {"grant": (AdminRoleGrantService, "final_access_administrator_conflict"),
              "profile": (ActorLifecycleService, "_conflict"),
              "link": (IdentityLinkLifecycleService, "_conflict")}
    if args.mutant != "none":
        owner, name = owners[args.mutant]
        setattr(owner, name, boundary_mutant(getattr(owner, name)))
    try:
        async with get_session_factory()() as session:
            try:
                await session.execute(text("SET LOCAL statement_timeout = '10s'"))
                await session.execute(text("SET LOCAL lock_timeout = '5s'"))
                repository = AdminAuthorizationRepository(session)
                await repository.lock_control()
                count = await repository.count_effective_access_administrators()
                if count != args.expected_count:
                    raise ValueError("unexpected_effective_count")
                locked = await repository.lock_actor_lifecycle_target(args.actor_id)
                if locked is None:
                    raise ValueError("missing_target")
                link, profile, grant = locked
                if (grant is None or str(grant.id) != str(args.grant_id)
                        or profile.status != "active" or link.status != "active"
                        or str(profile.id) != str(args.actor_id)
                        or str(link.actor_profile_id) != str(args.actor_id)):
                    raise ValueError("target_fact_mismatch")
                reason = derive_reason_digest("Isolated guard reproduction")
                results = {}
                conflict = await AdminRoleGrantService(session).final_access_administrator_conflict(args.grant_id)
                results["grant_revoke"] = "last_access_administrator" if conflict is not None else None
                for name, request_type, operation in (
                    ("profile_suspend", ActorProfileSuspendRequest, AuthorityOperation.ACTOR_PROFILE_SUSPEND),
                    ("profile_deactivate", ActorProfileDeactivateRequest, AuthorityOperation.ACTOR_PROFILE_DEACTIVATE),
                ):
                    request = request_type(operation=operation, actor_profile_id=args.actor_id, reason_digest=reason)
                    results[name] = await ActorLifecycleService(session)._conflict(
                        request, profile, link.status, grant is not None)
                link_tuple = await repository.lock_identity_link_lifecycle_target(UUID(str(link.id)))
                if link_tuple is None:
                    raise ValueError("missing_link")
                actual_link, actual_profile, actual_grant = link_tuple
                request = ActorIdentityLinkRevokeRequest(operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
                    identity_link_id=UUID(str(actual_link.id)), reason_digest=reason)
                results["link_revoke"] = await IdentityLinkLifecycleService(session)._conflict(
                    request, actual_link, actual_profile, actual_grant is not None)
                expected = "last_access_administrator" if args.expected_count == 1 else None
                failures = sorted(name for name, result in results.items() if result != expected)
                return {"result": "failed" if failures else "passed", "effective_count": count,
                        "checks": results, "failed_checks": failures, "mutant": args.mutant}
            finally:
                await session.rollback()
    finally:
        await dispose_engine()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolation-metadata", type=Path, required=True)
    parser.add_argument("--actor-id", type=UUID, required=True)
    parser.add_argument("--grant-id", type=UUID, required=True)
    parser.add_argument("--expected-count", type=int, choices=(1, 2), required=True)
    parser.add_argument("--mutant", choices=("none", "grant", "profile", "link"), default="none")
    args = parser.parse_args()
    try:
        result = asyncio.run(probe(args))
    except Exception as exc:
        # Unexpected driver/filesystem errors may contain credentials or stored data.
        code = (str(exc) if type(exc) in (ValueError, ProbeFailure)
                and str(exc) in FAILURE_CODES else "guard_probe_failed")
        print(json.dumps({"result": "infrastructure_failure", "error_kind": type(exc).__name__,
                          "error_code": code}))
        return 1
    print(json.dumps(result))
    return 0 if result["result"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
