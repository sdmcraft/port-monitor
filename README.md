# Porter

A lightweight Flask web app that lists every occupied TCP/UDP port on your Mac, shows the owning process, and lets you send `SIGTERM` or `SIGKILL` with one click.

## Getting started

```bash
git clone git@github.com:sdmcraft/port-monitor.git porter
cd porter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser. Click **Refresh** whenever you want to pull a fresh `lsof` snapshot and tap the **Port** column header to sort the table (each row is one listening port; if we can't detect one it falls back to the first active socket). The table now shows the full executable path, its launch folder, PID, parent PID (handy when a supervisor keeps respawning a process), and whether it's bound via IPv4 or IPv6, plus a confirmation dialog before sending a kill that lists every port the app owns.


> Tip: run the server with elevated privileges (e.g., `sudo -E python app.py`) if you need visibility into system processes you don't own.

## Running tests

Porter includes a comprehensive test suite with 100% code coverage. To run the tests:

```bash
# Make sure you're in the virtual environment
source .venv/bin/activate

# Run all tests
python -m pytest test_port_info.py -v

# Run tests with coverage report
python -m pytest test_port_info.py --cov=port_info --cov-report=term-missing

# Run a specific test class
python -m pytest test_port_info.py::TestKillProcess -v

# Run a specific test
python -m pytest test_port_info.py::TestKillProcess::test_kill_process_success -v
```

The test suite covers:
- Port collection and parsing (lsof output handling)
- Process information retrieval (command, PPID, CWD)
- Address parsing (IPv4, IPv6, connection states)
- Process management (signal sending, error handling)
- Integration tests for end-to-end flows

All tests use mocking to avoid real system calls, ensuring fast and isolated test execution.

## Publishing to GitHub

Already working from an initialized tree? Wire it to this repo:

```bash
git remote add origin git@github.com:sdmcraft/port-monitor.git
git push -u origin main
```

Teammates can then follow the steps above (`git clone git@github.com:sdmcraft/port-monitor.git porter`, create virtualenv, run `python app.py`) to get started locally.
