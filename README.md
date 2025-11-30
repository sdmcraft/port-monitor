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

Then open http://localhost:5000 in your browser. Click **Refresh** whenever you want to pull a fresh `lsof` snapshot and tap the **Port** column header to sort the table (each row is one listening port; if we can’t detect one it falls back to the first active socket). The table now shows the full executable path, its launch folder, PID, parent PID (handy when a supervisor keeps respawning a process), and whether it’s bound via IPv4 or IPv6, plus a confirmation dialog before sending a kill that lists every port the app owns.


> Tip: run the server with elevated privileges (e.g., `sudo -E python app.py`) if you need visibility into system processes you don't own.

## Publishing to GitHub

Already working from an initialized tree? Wire it to this repo:

```bash
git remote add origin git@github.com:sdmcraft/port-monitor.git
git push -u origin main
```

Teammates can then follow the steps above (`git clone git@github.com:sdmcraft/port-monitor.git porter`, create virtualenv, run `python app.py`) to get started locally.
