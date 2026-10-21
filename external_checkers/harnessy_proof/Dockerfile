# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89

# Networkless proof-claim checker for the local agent loop. The checker service
# starts it by platform-manifest digest with a read-only root and no network.
FROM python:3.12-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

COPY checker.py /opt/workstream/checker.py
USER 65532:65532
ENTRYPOINT ["python", "-I", "/opt/workstream/checker.py"]
