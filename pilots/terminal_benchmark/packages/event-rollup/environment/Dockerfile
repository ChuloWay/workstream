FROM python:3.12-slim-bookworm@sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN mkdir -p /workspace && chown 65532:65532 /workspace
WORKDIR /workspace
COPY --chown=65532:65532 workspace/ /workspace/
USER 65532:65532
