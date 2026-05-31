"""MCP runtime buffer tests."""

from plenipo.mcp.runtime import BufferedMessage, McpRuntime, McpRuntimeConfig


def test_drain_messages_since_and_limit() -> None:
    runtime = McpRuntime(
        McpRuntimeConfig(
            did='did:web:test.local',
            auth_secret_b64='AAAA',
            did_document_url='https://test.local/.well-known/did.json',
            relay_url='ws://localhost:4000/agent/websocket',
        )
    )
    runtime._buffer = [
        BufferedMessage(
            kind='deliver',
            envelope_id='01A',
            received_at_iso='2026-01-01T00:00:00+00:00',
        ),
        BufferedMessage(
            kind='deliver',
            envelope_id='01B',
            received_at_iso='2026-06-01T00:00:00+00:00',
        ),
    ]
    drained = runtime.drain_messages('2026-02-01T00:00:00Z', 10)
    assert len(drained) == 1
    assert drained[0].envelope_id == '01B'
    assert len(runtime._buffer) == 1
