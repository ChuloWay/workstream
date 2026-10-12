"""Deterministic ZIP bytes shared by current ART and TASK integration tests."""

from io import BytesIO
from zipfile import ZipFile, ZipInfo


async def byte_source(value: bytes):
    """Yield one immutable request body through the production async-byte port."""
    yield value


def submission_archive(
    path: str = "task.toml",
    *,
    primary_bytes: bytes = b"[task]\nname='proof'\n",
    extra_path: str | None = None,
    evidence_path: str = "evidence/results",
) -> bytes:
    """Return a timestamp-stable ZIP with one required artifact and evidence file."""
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        def write(name: str, value: bytes) -> None:
            archive.writestr(ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), value)

        write(path, primary_bytes)
        if extra_path is not None:
            write(extra_path, b"blocked\n")
        if path != evidence_path:
            write(evidence_path, b"verified\n")
    return output.getvalue()
