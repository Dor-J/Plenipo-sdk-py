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
