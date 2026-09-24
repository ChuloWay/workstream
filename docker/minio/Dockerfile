FROM golang:1.26.8-bookworm@sha256:a688600ca24f8a4d3ca77f95b0dd40704a9fc787c826660eb7ba0b641b8b175d AS build

ARG TARGETOS
ARG TARGETARCH
ARG MINIO_SOURCE_COMMIT=7aac2a2c5b7c882e68c1ce017d8256be2feea27f
ARG MINIO_SOURCE_SHA256=71794c2df26aad0cc99e8421c58b7aa2dd55969f979b0e7d1e931042e9fabcd6
ARG MINIO_VERSION=2026-02-12T20:18:48Z

ENV GOMAXPROCS=2 \
    GOPROXY=https://proxy.golang.org,direct \
    GOSUMDB=sum.golang.org \
    GOTOOLCHAIN=local

WORKDIR /source
RUN set -eux; \
    curl --fail --location --show-error --silent \
        "https://codeload.github.com/minio/minio/tar.gz/${MINIO_SOURCE_COMMIT}" \
        --output minio.tar.gz; \
    echo "${MINIO_SOURCE_SHA256}  minio.tar.gz" | sha256sum --check -; \
    mkdir /src; \
    tar --extract --gzip --file minio.tar.gz --directory /src --strip-components=1

WORKDIR /src
RUN go mod download && go mod verify
RUN set -eux; \
    release_tag="DEVELOPMENT.$(printf '%s' "${MINIO_VERSION}" | tr ':' '-')"; \
    short_commit="$(printf '%.12s' "${MINIO_SOURCE_COMMIT}")"; \
    mkdir /out; \
    CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" \
    go build -mod=readonly -p=2 \
        -tags kqueue \
        -trimpath \
        -ldflags="-s -w \
            -X github.com/minio/minio/cmd.Version=${MINIO_VERSION} \
            -X github.com/minio/minio/cmd.CopyrightYear=2026 \
            -X github.com/minio/minio/cmd.ReleaseTag=${release_tag} \
            -X github.com/minio/minio/cmd.CommitID=${MINIO_SOURCE_COMMIT} \
            -X github.com/minio/minio/cmd.ShortCommitID=${short_commit} \
            -X github.com/minio/minio/cmd.GOPATH=/go \
            -X github.com/minio/minio/cmd.GOROOT=/usr/local/go" \
        -o /out/minio .

FROM debian:12.15-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251

ARG MINIO_SOURCE_COMMIT=7aac2a2c5b7c882e68c1ce017d8256be2feea27f
ARG MINIO_SOURCE_SHA256=71794c2df26aad0cc99e8421c58b7aa2dd55969f979b0e7d1e931042e9fabcd6
ARG MINIO_VERSION=2026-02-12T20:18:48Z

LABEL org.opencontainers.image.title="MinIO for Workstream local and CI testing" \
      org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="${MINIO_SOURCE_COMMIT}" \
      org.opencontainers.image.version="${MINIO_VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      io.workstream.minio.source.url="https://codeload.github.com/minio/minio/tar.gz/${MINIO_SOURCE_COMMIT}" \
      io.workstream.minio.source.sha256="${MINIO_SOURCE_SHA256}"

RUN set -eux; \
    apt-get update; \
    apt-get install --yes --no-install-recommends ca-certificates curl; \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /out/minio /usr/bin/minio
COPY --from=build /src/dockerscripts/docker-entrypoint.sh /usr/bin/docker-entrypoint.sh
COPY --from=build /src/LICENSE /usr/share/licenses/minio/LICENSE
COPY --from=build /src/NOTICE /usr/share/licenses/minio/NOTICE
COPY --from=build /source/minio.tar.gz /usr/share/minio/source/minio.tar.gz

RUN chmod 0755 /usr/bin/minio /usr/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/bin/docker-entrypoint.sh"]
VOLUME ["/data"]
CMD ["minio"]
