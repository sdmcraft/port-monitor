"""
Module for resolving which port the Porter application itself should run on.

Handles automatic port selection when the preferred port is occupied.
"""

import os
import socket


ASSIGNED_PORT_ENV = "PORTER_ASSIGNED_PORT"


def find_available_port(preferred: int, host: str = "0.0.0.0", max_attempts: int = 50) -> int:
    """
    Find the first available port, starting at the preferred port.

    Probes ports sequentially by attempting to bind to them.

    Args:
        preferred: Starting port number to try.
        host: Host address to bind to (default: 0.0.0.0).
        max_attempts: Maximum number of ports to probe (default: 50).

    Returns:
        First available port number.

    Raises:
        RuntimeError: If no free port found after max_attempts.
    """
    candidate = preferred
    attempts = 0
    while attempts < max_attempts:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                candidate += 1
                attempts += 1
    raise RuntimeError(f"No free port found starting at {preferred} after {max_attempts} attempts.")


def resolve_run_port(host: str, preferred: int) -> int:
    """
    Determine which port the Flask dev server should bind to.

    Checks PORTER_ASSIGNED_PORT environment variable first, then falls back
    to finding an available port starting at the preferred port.
    Stores the selected port in the environment to maintain consistency
    across Flask's auto-reloader restarts.

    Args:
        host: Host address the server will bind to.
        preferred: Preferred port number to use.

    Returns:
        Port number to use for the server.
    """
    assigned = os.environ.get(ASSIGNED_PORT_ENV)
    if assigned:
        try:
            return int(assigned)
        except ValueError:
            os.environ.pop(ASSIGNED_PORT_ENV, None)

    port = find_available_port(preferred, host)
    os.environ[ASSIGNED_PORT_ENV] = str(port)
    if port != preferred:
        print(f"Port {preferred} is busy, switching to {port}.", flush=True)
    return port
