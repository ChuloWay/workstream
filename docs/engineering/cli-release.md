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
At planning time, the environment was absent; it is an external
prerequisite, not a repo file or an implicit workflow setting. Confirm branch protection and
the desired release operator. Do not use production credentials for this job;
the publisher needs only its short-lived `GITHUB_TOKEN` with `contents: write`.

For an approved source commit already on `main`, create an annotated
`cli-vMAJOR.MINOR.PATCH` tag and push that exact tag under repository controls.
Run “CLI release proof and publication” manually from `main`, supplying the
existing tag. The workflow freezes the tag-object ID and peeled commit, checks
main ancestry, runs all four native jobs, assembles exactly five assets and
waits for `cli-release` environment approval. The publisher checks the trusted
main workflow checkout, tag identity, asset allowlist, archive contents,
embedded versions and hashes before creating a draft release; it downloads and
rechecks uploaded assets before making that draft public. An interrupted run may
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
