"""Plenipo MCP server (scaffold)."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


@dataclass(frozen=True)
class PlenipoMCPOptions:
    """Configuration for :class:`PlenipoMCP`."""

    did_private_key: str
    relay_url: str


class PlenipoMCP:
    """MCP skill wrapper for Plenipo (scaffold)."""

    def __init__(self, *, did_private_key: str, relay_url: str) -> None:
        self._options = PlenipoMCPOptions(
            did_private_key=did_private_key,
            relay_url=relay_url,
        )

    def create_server(self) -> Server:
        server = Server('plenipo')

        @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name='plenipo_send',
                    description='Send an encrypted message to another agent by DID',
                    inputSchema={
                        'type': 'object',
                        'properties': {
                            'recipient_did': {'type': 'string'},
                            'message': {'type': 'string'},
                            'priority': {
                                'type': 'string',
                                'enum': ['low', 'normal', 'high'],
                            },
                        },
                        'required': ['recipient_did', 'message'],
                    },
                ),
                Tool(
                    name='plenipo_receive',
                    description='Poll incoming messages from other agents',
                    inputSchema={'type': 'object', 'properties': {}},
                ),
                Tool(
                    name='plenipo_discover',
                    description='Search the DID registry for agents',
                    inputSchema={'type': 'object', 'properties': {}},
                ),
                Tool(
                    name='plenipo_balance',
                    description='Check current token balance',
                    inputSchema={'type': 'object', 'properties': {}},
                ),
                Tool(
                    name='plenipo_did_create',
                    description='Generate a new DID document and key pair',
                    inputSchema={'type': 'object', 'properties': {}},
                ),
                Tool(
                    name='plenipo_identity',
                    description='Show the current local agent identity',
                    inputSchema={'type': 'object', 'properties': {}},
                ),
                Tool(
                    name='plenipo_declare_capabilities',
                    description='Declare or update agent capabilities in Core-hosted DID',
                    inputSchema={
                        'type': 'object',
                        'properties': {
                            'capabilities': {
                                'type': 'array',
                                'items': {'type': 'string'},
                            },
                            'replace': {'type': 'boolean'},
                        },
                        'required': ['capabilities'],
                    },
                ),
                Tool(
                    name='plenipo_purchase_bundle',
                    description='Purchase a token bundle via x402',
                    inputSchema={
                        'type': 'object',
                        'properties': {
                            'agent_did': {'type': 'string'},
                            'bundle_id': {'type': 'string'},
                            'relay_url': {'type': 'string'},
                        },
                        'required': ['agent_did', 'bundle_id'],
                    },
                ),
                Tool(
                    name='plenipo_delivery_status',
                    description='Get delivery status for an envelope',
                    inputSchema={
                        'type': 'object',
                        'properties': {
                            'envelope_id': {'type': 'string'},
                            'relay_url': {'type': 'string'},
                        },
                        'required': ['envelope_id'],
                    },
                ),
                Tool(
                    name='plenipo_mandate_prepare',
                    description='Prepare unsigned mandate JSON for operator signing',
                    inputSchema={
                        'type': 'object',
                        'properties': {
                            'agent_did': {'type': 'string'},
                            'operator_did': {'type': 'string'},
                            'relay_url': {'type': 'string'},
                        },
                        'required': ['agent_did', 'operator_did'],
                    },
                ),
            ]

        @server.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
            args = arguments or {}

            if name == 'plenipo_send':
                from plenipo.mcp.runtime import get_mcp_runtime

                runtime = get_mcp_runtime()
                ack = await runtime.send(
                    args['recipient_did'],
                    args['message'],
                    args.get('recipient_document_url'),
                )
                return [TextContent(type='text', text=str(ack))]

            if name == 'plenipo_receive':
                from plenipo.mcp.runtime import get_mcp_runtime

                runtime = get_mcp_runtime()
                await runtime.ensure_connected()
                messages = runtime.drain_messages(
                    args.get('since'),
                    int(args.get('limit', 100)),
                )
                payload = [
                    {
                        'kind': m.kind,
                        'envelope_id': m.envelope_id,
                        'sender_did': m.sender_did,
                        'recipient_did': m.recipient_did,
                        'plaintext': m.plaintext,
                        'ciphertext': m.ciphertext,
                        'received_at': m.received_at_iso,
                    }
                    for m in messages
                ]
                return [TextContent(type='text', text=str({'messages': payload}))]

            if name == 'plenipo_balance':
                from plenipo.mcp.runtime import get_mcp_runtime

                balance = await get_mcp_runtime().get_balance()
                return [TextContent(type='text', text=str({'balance': balance}))]

            if name == 'plenipo_discover':
                from plenipo.discover import discover_agents

                results = await discover_agents(
                    query=args.get('query'),
                    capability=args.get('capability'),
                )
                return [TextContent(type='text', text=str(results))]

            if name == 'plenipo_purchase_bundle':
                from plenipo.payments import purchase_bundle

                receipt = await purchase_bundle(
                    args.get('relay_url', 'http://localhost:4000'),
                    args['agent_did'],
                    args['bundle_id'],
                )
                return [TextContent(type='text', text=str(receipt))]

            if name == 'plenipo_mandate_prepare':
                from plenipo.payments import mandate_prepare

                result = await mandate_prepare(
                    args.get('relay_url', 'http://localhost:4000'),
                    {
                        'agent_did': args['agent_did'],
                        'operator_did': args['operator_did'],
                    },
                )
                return [TextContent(type='text', text=str(result))]

            if name == 'plenipo_delivery_status':
                from plenipo.delivery import get_delivery_status

                status = await get_delivery_status(
                    args.get('relay_url', 'http://localhost:4000'),
                    args['envelope_id'],
                )
                return [TextContent(type='text', text=str(status))]

            if name == 'plenipo_did_create':
                from plenipo.did import create_did_document

                domain = args.get('domain', 'agent.local')
                did_result = create_did_document(domain)
                return [
                    TextContent(
                        type='text',
                        text=str(
                            {
                                'did': did_result.did,
                                'document': did_result.document,
                                'privateKeys': {
                                    'auth': did_result.auth_secret_b64,
                                    'enc': did_result.enc_secret_b64,
                                },
                            }
                        ),
                    )
                ]

            if name == 'plenipo_identity':
                from plenipo.identity.provision import ensure_identity

                identity = await ensure_identity()
                return [
                    TextContent(
                        type='text',
                        text=str(
                            {
                                'did': identity.did,
                                'did_document_url': identity.did_document_url,
                                'capabilities': identity.capabilities,
                                'relay_url': identity.relay_url,
                                'registry_url': identity.registry_url,
                                'core_url': identity.core_url,
                            }
                        ),
                    )
                ]

            if name == 'plenipo_declare_capabilities':
                from plenipo.identity.capabilities import declare_capabilities

                updated = await declare_capabilities(
                    [str(cap) for cap in args['capabilities']],
                    replace=bool(args.get('replace', False)),
                )
                return [
                    TextContent(
                        type='text',
                        text=str(
                            {
                                'did': updated.did,
                                'capabilities': updated.capabilities,
                            }
                        ),
                    )
                ]

            return [TextContent(type='text', text=f'{name} requires programmatic client setup.')]

        return server

    async def run_stdio(self) -> None:
        server = self.create_server()
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())


async def bootstrap_mcp_runtime() -> None:
    """Ensures identity exists and initializes the MCP runtime."""
    from plenipo.mcp.runtime import McpRuntime, load_mcp_config, set_mcp_runtime

    config = await load_mcp_config()
    set_mcp_runtime(McpRuntime(config))


def main() -> None:
    """Run the MCP server over stdio with agent-first identity bootstrap."""
    asyncio.run(_main_async())


async def _main_async() -> None:
    await bootstrap_mcp_runtime()
    relay_url = os.environ.get('PLENIPO_RELAY_URL', 'ws://localhost:4000/agent/websocket')
    skill = PlenipoMCP(
        did_private_key=os.environ.get('PLENIPO_AUTH_SECRET_B64', 'bootstrap'),
        relay_url=relay_url,
    )
    await skill.run_stdio()


def load_mcp_config_from_env() -> None:
    """Validates MCP configuration from env or identity.json at startup."""
    from plenipo.mcp.runtime import load_mcp_config_from_env as _load

    _load()


if __name__ == '__main__':
    main()
