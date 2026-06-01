"""MCP CLI module smoke tests."""


def test_mcp_main_module_exports_server_main() -> None:
    import plenipo.mcp.__main__ as entry
    from plenipo.mcp.server import main

    assert entry.main is main
