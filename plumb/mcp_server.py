"""Compatibility launcher; implementation lives in plumb.interfaces.mcp_server."""
from plumb.interfaces.mcp_server import mcp

if __name__ == "__main__":
    mcp.run()
