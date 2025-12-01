# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Porter is a Flask-based web application for monitoring and managing TCP/UDP ports on macOS. It provides a web interface to view all occupied ports, the processes that own them, and send kill signals (SIGTERM/SIGKILL) to those processes.

## Development Setup

```bash
# Clone and setup
git clone git@github.com:sdmcraft/port-monitor.git porter
cd porter

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the development server
python app.py
```

The app runs on http://localhost:5000 by default. If port 5000 is occupied, it will automatically find the next available port.

## Running with Elevated Privileges

To see system processes you don't own:
```bash
sudo -E python app.py
```

## Architecture

### Backend (app.py)

**Core Architecture:**
- Flask application serving both API endpoints and static files
- Uses `lsof` system command to gather port information
- Process details gathered via `ps` and `lsof -a -p <pid> -d cwd`
- LRU caching (`@functools.lru_cache`) for process metadata queries to improve performance

**Key Components:**
1. **Port Collection Pipeline** (app.py:113-126):
   - `_collect_ports()` → `_parse_lsof_output()` → enriched port entries
   - Each entry augmented with process details (PPID, full command path, CWD)

2. **Process Information Gathering** (app.py:129-186):
   - `_get_process_command(pid)`: Full command path via `ps -o command=`
   - `_get_parent_pid(pid)`: Parent PID via `ps -o ppid=`
   - `_get_process_cwd(pid)`: Working directory via `lsof -a -p <pid> -d cwd -Fn`
   - All cached with `@functools.lru_cache(maxsize=1024)`

3. **Address Parsing** (app.py:27-47):
   - `_split_host_port()` handles IPv4, IPv6 bracketed addresses, and connection states
   - Extracts host and port from lsof output format

4. **Port Auto-selection** (app.py:267-296):
   - `_resolve_run_port()` checks `PORTER_ASSIGNED_PORT` env var
   - Falls back to `_find_available_port()` which probes up to 50 ports
   - Automatically switches if preferred port is busy

**API Endpoints:**
- `GET /api/ports` - Returns all port data with process details
- `POST /api/kill` - Send SIGTERM to a process (requires `pid` in JSON body)
- `POST /api/force-kill` - Send SIGKILL to a process (requires `pid` in JSON body)
- `GET /` - Serves static HTML interface

### Frontend (static/*)

**Architecture:**
- Vanilla JavaScript (ES6 modules) with no framework dependencies
- Client-side grouping and sorting of port data
- Modal confirmation dialog for kill operations

**Key Logic in app.js:**
1. **Process Grouping** (app.js:47-91):
   - `groupByProcess()` consolidates multiple sockets per process
   - Groups by `command:pid:user` key
   - Distinguishes listening ports from active connections
   - Prefers listening ports for display, falls back to first active socket

2. **Row Building** (app.js:93-125):
   - `buildPortRows()` creates one row per listening port per process
   - If no listening ports, shows one row with first active connection
   - Attaches all socket details to each row for the "Connections" column

3. **Sorting** (app.js:127-143):
   - Port column toggles ascending/descending sort
   - Numeric port comparison, falls back to alphabetical by command name
   - Non-numeric ports sorted to end (using `Number.POSITIVE_INFINITY`)

4. **Kill Confirmation Flow** (app.js:170-189):
   - Modal shows all ports owned by the process before kill
   - Separate buttons for SIGTERM ("Kill") and SIGKILL ("Force")
   - Automatically refreshes port list after kill attempt

## Key Design Decisions

**Why group by process rather than show all sockets individually?**
- Most processes open multiple sockets (IPv4/IPv6, listening + connections)
- Grouping provides clearer overview of which apps are using ports
- Kill actions apply to entire process, not individual sockets

**Why prefer listening ports over established connections?**
- Listening ports are what users typically think of as "the port the app uses"
- Established connections are often ephemeral and less useful for identification
- Fallback to first active socket when no listening port exists

**Why use `lsof` instead of parsing `/proc` or `netstat`?**
- This is a macOS-focused tool; `lsof` is standard and reliable on macOS
- Provides unified interface for both port and process info
- Rich output format with connection states and protocol details

## Common Development Tasks

**Testing with a specific port occupied:**
```bash
# In one terminal
python -m http.server 8000

# In another, run Porter
python app.py
# Now you can see port 8000 in the UI
```

**Testing elevated privileges:**
```bash
sudo -E python app.py
# Should now see system processes like `launchd`, `mDNSResponder`
```

**Modifying the default port:**
```bash
PORT=8080 python app.py
# Or set PORTER_ASSIGNED_PORT=8080 to skip auto-detection
```

## Dependencies

- **Flask**: Web framework (only production dependency)
- **lsof**: System utility (must be available on PATH)
- **ps**: System utility (standard on macOS/Unix)

## macOS-Specific Behavior

This tool is designed for macOS and relies on:
- `lsof` command-line flags and output format
- `ps` BSD-style options (`-o command=`, `-o ppid=`)
- Unix signal handling (SIGTERM, SIGKILL)

Porting to Linux would require testing and potentially adjusting command flags and parsing logic.
- Before making any code changes, provide a plan first