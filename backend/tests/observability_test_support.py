"""Focused test adapter for process-local observability resources."""

from __future__ import annotations

from dataclasses import dataclass

from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SpanExporter

from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.interfaces.observability import (
    OBSERVABILITY_EXPORT_CAPABILITY_KEY,
    ObservabilityExporterBundle,
)


@dataclass(frozen=True, slots=True)
class FakeObservabilityExportAdapter:
    """Return one test-owned exporter bundle through the production port."""

    span_exporter: SpanExporter
    metric_reader: MetricReader

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        return ExternalServiceAdapterIdentity(
            OBSERVABILITY_EXPORT_CAPABILITY_KEY,
            "test_memory",
        )

    def create_exporters(self) -> ObservabilityExporterBundle:
        return ObservabilityExporterBundle(self.span_exporter, self.metric_reader)


def fake_export_adapter(
    span_exporter: SpanExporter,
    metric_reader: MetricReader | None = None,
) -> FakeObservabilityExportAdapter:
    """Build the shared fake through the same typed production port."""
    return FakeObservabilityExportAdapter(
        span_exporter,
        metric_reader or InMemoryMetricReader(),
    )
