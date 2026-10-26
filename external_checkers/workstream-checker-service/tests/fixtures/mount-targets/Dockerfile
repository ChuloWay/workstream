# Test-only image. Supply an already pinned local fixture as BASE_IMAGE.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG MOUNT_ROOT
RUN test "$MOUNT_ROOT" = work -o "$MOUNT_ROOT" = tmp && \
    rm -rf "/$MOUNT_ROOT" && ln -s /sys/fs/cgroup "/$MOUNT_ROOT"
