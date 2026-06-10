"""Prometheus text metrics for the local sidecar."""

from __future__ import annotations

from plenipo.runtime import PlenipoAgentRuntime
from plenipo.sidecar.models import SERVICE_NAME, SIDECAR_VERSION


def render_sidecar_metrics(runtime: PlenipoAgentRuntime) -> str:
    """Renders sanitized local sidecar metrics in Prometheus text format."""
    store = runtime.store
    lines: list[str] = []

    _append(
        lines,
        'plenipo_sidecar_build_info',
        'Sidecar build information.',
        'gauge',
        1,
        {'service': SERVICE_NAME, 'version': SIDECAR_VERSION},
    )
    connected = bool(getattr(getattr(runtime, '_client', None), 'connected', False))
    _append(
        lines,
        'plenipo_sidecar_relay_connected',
        'Relay WebSocket connection state.',
        'gauge',
        1 if connected else 0,
    )
    for status, count in store.count_outbox_by_status().items():
        _append(
            lines,
            'plenipo_sidecar_outbox_rows',
            'Local outbox rows by status.',
            'gauge',
            count,
            {'status': status},
        )
    _append(
        lines,
        'plenipo_sidecar_receipts',
        'Local persisted delivery receipts.',
        'gauge',
        store.count_receipts(),
    )
    _append(
        lines,
        'plenipo_sidecar_inbox_messages',
        'Encrypted-at-rest inbox rows.',
        'gauge',
        store.count_inbox_messages(),
    )
    _append(
        lines,
        'plenipo_sidecar_events_pending_delivery',
        'Durable sidecar events not delivered to a local client.',
        'gauge',
        store.count_pending_sidecar_events(),
    )
    for event_type, count in store.count_sidecar_events_by_type().items():
        _append(
            lines,
            'plenipo_sidecar_events',
            'Durable sidecar events by type.',
            'gauge',
            count,
            {'event_type': event_type},
        )

    return '\n'.join(lines) + '\n'


def _append(
    lines: list[str],
    name: str,
    help_text: str,
    metric_type: str,
    value: int | float,
    labels: dict[str, str] | None = None,
) -> None:
    help_line = f'# HELP {name} {help_text}'
    if help_line not in lines:
        lines.append(help_line)
        lines.append(f'# TYPE {name} {metric_type}')
    label_text = ''
    if labels:
        rendered = ','.join(
            f'{key}="{_escape_label(value)}"' for key, value in sorted(labels.items())
        )
        label_text = f'{{{rendered}}}'
    lines.append(f'{name}{label_text} {value}')


def _escape_label(value: str) -> str:
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
