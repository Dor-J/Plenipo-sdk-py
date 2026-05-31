"""Plenipo MCP server (scaffold)."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

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

        @server.list_tools()
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

        @server.call_tool()
        async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
            args = arguments or {}

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
                result = create_did_document(domain)
                return [
                    TextContent(
                        type='text',
                        text=str(
                            {
                                'did': result.did,
                                'document': result.document,
                                'privateKeys': {
                                    'auth': result.auth_secret_b64,
                                    'enc': result.enc_secret_b64,
                                },
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


def main() -> None:
    """Run the MCP server over stdio using environment variables."""
    skill = PlenipoMCP(
        did_private_key=os.environ['PLENIPO_DID_PRIVATE_KEY'],
        relay_url=os.environ.get('PLENIPO_RELAY_URL', 'wss://relay.plenipo.dev'),
    )
    asyncio.run(skill.run_stdio())


if __name__ == '__main__':
    main()
