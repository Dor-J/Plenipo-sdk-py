"""Tests for the Plenipo MCP server scaffold."""

from plenipo.mcp.server import PlenipoMCP
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from plenipo.mcp.runtime import BufferedMessage


def test_create_server_lists_tools() -> None:
    skill = PlenipoMCP(did_private_key='test-key', relay_url='wss://relay.example')
    server = skill.create_server()
    assert server is not None


async def test_mcp_server_tool_handlers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    skill = PlenipoMCP(did_private_key='test-key', relay_url='wss://relay.example')
    server = skill.create_server()
    tools = await server.request_handlers[ListToolsRequest](ListToolsRequest())
    assert {tool.name for tool in tools.root.tools} >= {
        'plenipo_send',
        'plenipo_receive',
        'plenipo_balance',
        'plenipo_discover',
        'plenipo_purchase_bundle',
        'plenipo_mandate_prepare',
        'plenipo_delivery_status',
        'plenipo_did_create',
    }

    class Runtime:
        async def send(
            self,
            recipient_did: str,
            message: str,
            recipient_document_url: str | None = None,
        ) -> dict[str, object]:
            return {
                'status': 'queued',
                'recipient_did': recipient_did,
                'message': message,
                'recipient_document_url': recipient_document_url,
            }

        async def ensure_connected(self) -> None:
            return None

        def drain_messages(self, since: str | None, limit: int) -> list[BufferedMessage]:
            assert since is None
            assert limit == 1
            return [
                BufferedMessage(
                    kind='deliver',
                    envelope_id='01J',
                    sender_did='did:web:sender.local',
                    recipient_did='did:web:agent.local',
                    ciphertext='cipher',
                    plaintext='hello',
                    received_at_iso='2026-06-01T00:00:00Z',
                )
            ]

        async def get_balance(self) -> int:
            return 42

    runtime = Runtime()
    monkeypatch.setattr('plenipo.mcp.runtime.get_mcp_runtime', lambda: runtime)

    async def fake_discover(**_kwargs: object) -> list[dict[str, object]]:
        return [{'did': 'did:web:agent.local'}]

    async def fake_purchase(*_args: object) -> dict[str, object]:
        return {'tokens': 1000, 'balance': 1000}

    async def fake_mandate(*_args: object) -> dict[str, object]:
        return {'mandate': {'agent_did': 'did:web:agent.local'}}

    async def fake_delivery(*_args: object) -> dict[str, object]:
        return {'status': 'delivered'}

    monkeypatch.setattr('plenipo.discover.discover_agents', fake_discover)
    monkeypatch.setattr('plenipo.payments.purchase_bundle', fake_purchase)
    monkeypatch.setattr('plenipo.payments.mandate_prepare', fake_mandate)
    monkeypatch.setattr('plenipo.delivery.get_delivery_status', fake_delivery)

    async def call(name: str, arguments: dict[str, object] | None = None) -> str:
        result = await server.request_handlers[CallToolRequest](
            CallToolRequest(
                params=CallToolRequestParams(
                    name=name,
                    arguments=arguments,
                )
            )
        )
        return result.root.content[0].text

    assert 'queued' in await call(
        'plenipo_send',
        {'recipient_did': 'did:web:recipient.local', 'message': 'hello'},
    )
    assert 'messages' in await call('plenipo_receive', {'limit': 1})
    assert '42' in await call('plenipo_balance')
    assert 'did:web:agent.local' in await call('plenipo_discover', {'query': 'agent'})
    assert '1000' in await call(
        'plenipo_purchase_bundle',
        {'agent_did': 'did:web:agent.local', 'bundle_id': 'starter'},
    )
    assert 'mandate' in await call(
        'plenipo_mandate_prepare',
        {'agent_did': 'did:web:agent.local', 'operator_did': 'did:web:operator.local'},
    )
    assert 'delivered' in await call('plenipo_delivery_status', {'envelope_id': '01J'})
    assert 'did:web:agent.local' in await call('plenipo_did_create', {'domain': 'agent.local'})
    assert 'requires programmatic client setup' in await call('unknown_tool')


def test_mcp_main_uses_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from plenipo.mcp import server as server_module

    called: list[str] = []

    def fake_load() -> None:
        called.append('load')

    async def fake_run_stdio(self: PlenipoMCP) -> None:
        called.append(self._options.relay_url)

    monkeypatch.setenv('PLENIPO_AUTH_SECRET_B64', 'AUTH')
    monkeypatch.setenv('PLENIPO_RELAY_URL', 'wss://relay.example')
    monkeypatch.setattr(server_module, 'load_mcp_config_from_env', fake_load)
    monkeypatch.setattr(PlenipoMCP, 'run_stdio', fake_run_stdio)

    server_module.main()

    assert called == ['load', 'wss://relay.example']
