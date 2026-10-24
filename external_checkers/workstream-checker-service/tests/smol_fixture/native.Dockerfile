FROM scratch
COPY runtime_fixture /checker
ENTRYPOINT ["/checker"]
