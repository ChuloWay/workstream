# CLI release operation

The only CLI distribution channel is GitHub Releases, with annotated tags of
the form `cli-vMAJOR.MINOR.PATCH`. This is separate from the unreleased Workstream
backend/product version. The [CLI user guide](../../cli/README.md#install-a-released-binary)
lists the four supported native targets and installation/verification steps.
Release archives contain one executable and the license; `SHA256SUMS` covers all
four archives. The embedded CLI version includes the full source commit SHA.

The [CLI release workflow](../../.github/workflows/cli-release.yml) runs a
read-only preview on relevant pull requests. All four native runners must pass
repeated deterministic builds and install/API/upgrade/rollback/removal smoke
before a release is considered. Preview artifacts are not public distribution.
The native loopback API fixture proves authenticated transport from each
installed executable; it does not replace the existing Linux public-API
integration suite or prove every deployed backend version.

Before the first release, a repository administrator must configure the
`cli-release` GitHub environment with required human reviewers and a deployment
branch restriction to `main`, with self-review prevention enabled, then inspect
those settings. The workflow queries the environment API in both preparation
and publication and fails closed if those controls are absent or unavailable.
At planning time, the environment could not be verified (GitHub API returned
404, which could mean absent or inaccessible). It is an external prerequisite,
not a repo file or an implicit workflow setting. Confirm branch protection and
the desired release operator. Do not use production credentials for this job;
the publisher uses only its short-lived `GITHUB_TOKEN` with `contents: write`
and `actions: read`.

A repository administrator must also configure one active repository tag ruleset
named `Workstream CLI immutable tags`, targeting exactly `refs/tags/cli-v*`,
with update and deletion restricted and no bypass actors. This protects the
exact source tag across draft creation and publication. The workflow checks
the visible ruleset before native release builds and again before publication;
it cannot create or repair that repository policy. GitHub omits the bypass list
from this read-only token response. Before approving the `cli-release`
environment, an independent repository administrator must inspect and record
that the ruleset has no bypass actors, then ensure the tag still points to the
reviewed commit. Do not treat an omitted bypass list as empty. A trusted
administrator could later alter policy; this is a residual operational trust
boundary. No such ruleset was verified at planning time. Classic tag protection
alone is not accepted by this workflow because it does not prove the exact
no-bypass contract here.

For an approved source commit already on `main`, create an annotated
`cli-vMAJOR.MINOR.PATCH` tag and push that exact tag under repository controls.
Run “CLI release proof and publication” manually from `main`, supplying the
existing tag. The workflow freezes the tag-object ID and peeled commit, checks
main ancestry, runs all four native jobs, assembles exactly five assets and
waits for `cli-release` environment approval. The publisher checks the trusted
main workflow checkout, tag identity, asset allowlist, archive contents,
embedded versions and hashes before creating a draft release; it downloads and
rechecks uploaded assets and the tag immediately before and after making that
draft public. These checks do not make a mutable tag atomic; enforced protection
and the administrator bypass inspection are required. An interrupted run may
leave a draft; inspect it and resolve it deliberately rather than rerunning
against a possibly existing release.

After publication, independently download all five assets from the public
release page, verify their hashes and run one clean installation on each
supported platform. A later release should also exercise upgrade and rollback
against the actual previous published binary; the first release can prove only
the same-source installation mechanics. Neither SHA-256 checksums nor release
page access constitute a cryptographic signature. macOS binaries are not signed
or notarized. A change in signing, package channels or supported platforms
requires a new bounded decision and proof.
