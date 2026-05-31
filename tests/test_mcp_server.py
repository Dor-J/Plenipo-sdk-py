"""Tests for the Plenipo MCP server scaffold."""

from plenipo.mcp.server import PlenipoMCP


def test_create_server_lists_tools() -> None:
    skill = PlenipoMCP(did_private_key='test-key', relay_url='wss://relay.example')
    server = skill.create_server()
    assert server is not None
