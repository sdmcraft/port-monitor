"""
Module for collecting port information and process details from the system.

Uses lsof and ps commands to gather comprehensive information about
occupied TCP/UDP ports and their owning processes.
"""

import functools
import os
import shutil
import signal
import subprocess
from typing import List, Dict, Tuple
from flask import abort


class PortFetchError(RuntimeError):
    """Raised when the list of occupied ports cannot be retrieved."""


def _get_lsof_path() -> str:
    """
    Locate the lsof executable on the system.

    Returns:
        str: Full path to the lsof command.

    Raises:
        PortFetchError: If lsof is not found in PATH.
    """
    path = shutil.which("lsof")
    if not path:
        raise PortFetchError("The 'lsof' command is required but was not found on this system.")
    return path


def _split_host_port(address: str) -> Tuple[str, str]:
    """
    Parse host and port from an lsof address string.

    Handles various formats including:
    - IPv4: "127.0.0.1:8080"
    - IPv6: "[::1]:8080"
    - Connection states: "127.0.0.1:8080->192.168.1.1:443"

    Args:
        address: Address string from lsof output.

    Returns:
        Tuple of (host, port). Port may be empty string if not found.
    """
    host = address
    port = ""
    if not address:
        return host, port

    if "->" in address:
        host = address.split("->", 1)[0]

    if host.startswith("[") and "]" in host:
        closing = host.find("]")
        bracketed = host[1:closing]
        tail = host[closing + 1 :]
        if tail.startswith(":"):
            port = tail[1:]
        host = bracketed
    elif ":" in host:
        parts = host.rsplit(":", 1)
        if len(parts) == 2:
            host, port = parts
    return host or address, port


def _parse_lsof_output(output: str) -> List[Dict]:
    """
    Parse lsof command output into structured port entries.

    Extracts socket information and enriches each entry with process details
    including PID, PPID, command path, and working directory.

    Args:
        output: Raw stdout from lsof command.

    Returns:
        List of dictionaries, each containing port and process information.
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) <= 1:
        return []

    entries: List[Dict] = []
    header_skipped = False
    for line in lines:
        if not header_skipped:
            header_skipped = True
            continue

        parts = line.split()
        if len(parts) < 9:
            # Unexpected line format, skip it.
            continue

        command, pid_str, user, fd, type_, device, size_off, node = parts[:8]
        name_parts = parts[8:]
        protocol = node
        state = ""

        if name_parts and name_parts[-1].startswith("(") and name_parts[-1].endswith(")"):
            state = name_parts[-1][1:-1]
            name_parts = name_parts[:-1]

        address = " ".join(name_parts)
        host, port = _split_host_port(address)

        try:
            pid = int(pid_str)
        except ValueError:
            # Skip rows with non-numeric PIDs (shouldn't happen, but be safe)
            continue

        process_details = _get_process_details(pid)

        entries.append(
            {
                "command": command,
                "pid": pid,
                "ppid": process_details.get("ppid"),
                "user": user,
                "fd": fd,
                "type": type_,
                "protocol": protocol,
                "address": address,
                "host": host,
                "port": port,
                "state": state,
                "full_command": process_details.get("command_path") or command,
                "cwd": process_details.get("cwd") or "",
                "details": {
                    "device": device,
                    "size_off": size_off,
                    "node": node,
                },
            }
        )

    return entries


def collect_ports() -> List[Dict]:
    """
    Collect all TCP and UDP port information from the system.

    Executes lsof with flags:
    - -n: Don't resolve hostnames (faster)
    - -P: Don't resolve port names (show numbers)
    - -iTCP -iUDP: Show both TCP and UDP sockets

    Returns:
        List of port entries with enriched process information.

    Raises:
        PortFetchError: If lsof command fails or is not found.
    """
    lsof = _get_lsof_path()
    cmd = [lsof, "-nP", "-iTCP", "-iUDP"]
    try:
        completed = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise PortFetchError(exc.stderr.strip() or "Failed to collect port information.") from exc
    return _parse_lsof_output(completed.stdout)


@functools.lru_cache(maxsize=1024)
def _get_process_field(pid: int, field: str) -> str:
    """
    Generic function to get a process field using ps.

    Results are cached to avoid repeated subprocess calls.

    Args:
        pid: Process ID.
        field: ps output field (e.g., "command=", "ppid=").

    Returns:
        Field value as string, or empty string if process not found.
    """
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", field],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def _get_process_command(pid: int) -> str:
    """
    Get the full command path for a process.

    Uses ps to retrieve the complete command line including path.
    Results are cached via _get_process_field.

    Args:
        pid: Process ID.

    Returns:
        Full command path, or empty string if process not found.
    """
    return _get_process_field(pid, "command=")


def _get_parent_pid(pid: int) -> int | None:
    """
    Get the parent process ID for a given process.

    Useful for identifying supervisor processes that may respawn killed processes.
    Results are cached via _get_process_field.

    Args:
        pid: Process ID.

    Returns:
        Parent PID as integer, or None if not found or invalid.
    """
    value = _get_process_field(pid, "ppid=")
    return int(value) if value.isdigit() else None


@functools.lru_cache(maxsize=1024)
def _get_process_cwd(pid: int) -> str:
    """
    Get the current working directory of a process.

    Uses lsof with special flags:
    - -a: AND conditions together
    - -p <pid>: Specific process
    - -d cwd: Only show current working directory
    - -Fn: Output format with 'n' prefix for names

    Results are cached to avoid repeated subprocess calls.

    Args:
        pid: Process ID.

    Returns:
        Working directory path, or empty string if not found.
    """
    lsof = _get_lsof_path()
    cmd = [lsof, "-a", "-p", str(pid), "-d", "cwd", "-Fn"]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError:
        return ""

    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return line[1:].strip()
    return ""


def _get_process_details(pid: int) -> Dict[str, str]:
    """
    Gather comprehensive process information for a PID.

    Consolidates parent PID, full command path, and working directory
    into a single dictionary. All lookups are cached individually.

    Args:
        pid: Process ID.

    Returns:
        Dictionary with keys: ppid, command_path, cwd.
    """
    return {
        "ppid": _get_parent_pid(pid),
        "command_path": _get_process_command(pid),
        "cwd": _get_process_cwd(pid),
    }


def kill_process(pid: int, sig: int) -> None:
    """
    Send a signal to a process.

    Wraps os.kill with proper error handling and HTTP error responses.

    Args:
        pid: Process ID to signal.
        sig: Signal number (e.g., signal.SIGTERM or signal.SIGKILL).

    Raises:
        HTTP 404: Process not found.
        HTTP 403: Insufficient permissions.
        HTTP 500: Other errors.
    """
    try:
        os.kill(pid, sig)
    except ProcessLookupError as exc:
        abort(404, description=f"Process {pid} was not found.")
    except PermissionError as exc:
        abort(403, description=f"Insufficient permissions to signal process {pid}.")
    except Exception as exc:  # pylint: disable=broad-except
        abort(500, description=f"Failed to signal process {pid}: {exc}")
