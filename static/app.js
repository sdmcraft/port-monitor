const tableBody = document.querySelector('#ports-table tbody');
const refreshBtn = document.querySelector('#refresh-btn');
const statusMessage = document.querySelector('#status-message');
const lastUpdated = document.querySelector('#last-updated');
const portHeader = document.querySelector('#port-header');
const confirmModal = document.querySelector('#confirm-modal');
const confirmMessage = document.querySelector('#confirm-message');
const confirmCancel = document.querySelector('#confirm-cancel');
const confirmAccept = document.querySelector('#confirm-accept');

let sortState = { direction: 'asc' };
let cachedPorts = [];
let pendingKill = null;

const stateClass = (state) => {
  if (!state) return 'unknown';
  const normalized = state.toLowerCase();
  if (normalized.includes('listen')) return 'listening';
  if (normalized.includes('established')) return 'established';
  return 'unknown';
};

const formatState = (state) => state || '—';

const setStatus = (message, tone = 'neutral') => {
  statusMessage.textContent = message;
  statusMessage.dataset.tone = tone;
};

const normalizeSockets = (entry) => ({
  protocol: entry.protocol,
  host: entry.host || '—',
  port: entry.port || '—',
  state: entry.state,
  address: entry.address || '—',
  family: entry.type || entry.protocol || '—',
});

const uniquePortList = (sockets) => [
  ...new Set(
    sockets
      .map((socket) => socket.port)
      .filter((value) => value && value !== '—')
  ),
];

const groupByProcess = (ports) => {
  const groups = new Map();

  ports.forEach((entry) => {
    const pid = entry.pid ?? 'unknown';
    const key = `${entry.command}:${pid}:${entry.user}`;
    if (!groups.has(key)) {
      groups.set(key, {
        command: entry.command,
        pid: entry.pid,
        user: entry.user,
        sockets: [],
        fullCommand: entry.full_command || entry.command || '—',
        cwd: entry.cwd || '—',
        ppid: entry.ppid ?? '—',
      });
    }
    const group = groups.get(key);
    if ((!group.fullCommand || group.fullCommand === '—') && entry.full_command) {
      group.fullCommand = entry.full_command;
    }
    if ((!group.cwd || group.cwd === '—') && entry.cwd) {
      group.cwd = entry.cwd;
    }
    if ((group.ppid === undefined || group.ppid === '—') && entry.ppid !== undefined) {
      group.ppid = entry.ppid;
    }
    group.sockets.push(normalizeSockets(entry));
  });

  return Array.from(groups.values()).map((group) => {
    const listeningSockets = group.sockets.filter(
      (socket) => socket.state && socket.state.toLowerCase().includes('listen')
    );
    const listeningPorts = uniquePortList(listeningSockets);
    const fallbackPorts = uniquePortList(group.sockets);
    const processPorts = listeningPorts.length ? listeningPorts : fallbackPorts;

    return {
      ...group,
      listeningPorts,
      processPorts: processPorts.length ? processPorts : ['—'],
    };
  });
};

const buildPortRows = (processGroups) => {
  const rows = [];

  processGroups.forEach((group) => {
    const portList = group.listeningPorts.length ? group.listeningPorts : group.processPorts;
    const targets = portList.length ? portList : ['—'];

    targets.forEach((portValue) => {
      const socketsForPort = group.sockets.filter((socket) => socket.port === portValue);
      const numericPort = Number.parseInt(portValue, 10);

      rows.push({
        command: group.command,
        pid: group.pid,
        user: group.user,
        displayPort: portValue,
        numericPort: Number.isFinite(numericPort) ? numericPort : Number.POSITIVE_INFINITY,
        sockets: socketsForPort.length ? socketsForPort : group.sockets,
        processPorts: group.processPorts,
        family:
          (socketsForPort[0]?.family ||
            group.sockets[0]?.family ||
            group.sockets[0]?.protocol) ??
          '—',
        fullCommand: group.fullCommand || '—',
        cwd: group.cwd || '—',
        ppid: group.ppid,
      });
    });
  });

  return rows;
};

const sortRows = (rows) => {
  const sorted = rows.slice().sort((a, b) => {
    if (a.numericPort === b.numericPort) {
      return a.command.localeCompare(b.command);
    }
    return sortState.direction === 'asc'
      ? a.numericPort - b.numericPort
      : b.numericPort - a.numericPort;
  });
  return sorted;
};

const updateSortIndicator = () => {
  if (portHeader) {
    portHeader.dataset.direction = sortState.direction;
  }
};

const triggerKill = async (pid, force = false) => {
  const endpoint = force ? '/api/force-kill' : '/api/kill';
  setStatus(`Sending ${force ? 'SIGKILL' : 'SIGTERM'} to ${pid}…`, 'info');
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || 'Unable to signal process');
    }
    setStatus(payload.message || 'Signal sent.', 'success');
    await fetchPorts();
  } catch (error) {
    setStatus(error.message, 'error');
  }
};

const formatPortList = (ports) => {
  const clean = (ports || []).filter((value) => value && value !== '—');
  return clean.length ? clean.join(', ') : 'unknown ports';
};

const closeKillDialog = () => {
  if (!confirmModal) return;
  confirmModal.classList.add('hidden');
  confirmModal.setAttribute('aria-hidden', 'true');
  pendingKill = null;
};

const openKillDialog = (group, force = false) => {
  if (!confirmModal) {
    triggerKill(group.pid, force);
    return;
  }

  const portList = formatPortList(group.processPorts);
  confirmMessage.textContent = `${group.command} is listening on ports ${portList}. Killing it will free up all these ports.`;
  confirmAccept.textContent = force ? 'Force Kill' : 'Kill';
  confirmModal.classList.remove('hidden');
  confirmModal.setAttribute('aria-hidden', 'false');
  pendingKill = { pid: group.pid, force };
};

const renderRows = (ports) => {
  cachedPorts = ports;
  tableBody.innerHTML = '';

  const grouped = groupByProcess(ports);
  const portRows = sortRows(buildPortRows(grouped));

  if (!portRows.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 10;
    cell.className = 'empty';
    cell.textContent = 'No occupied ports detected.';
    row.appendChild(cell);
    tableBody.appendChild(row);
    return;
  }

  portRows.forEach((group) => {
    const row = document.createElement('tr');

    const addCell = (text, className) => {
      const td = document.createElement('td');
      td.textContent = text;
      if (className) {
        td.className = className;
        if (className.includes('path-cell') || className.includes('app-cell')) {
          td.title = text;
        }
      }
      row.appendChild(td);
    };

    addCell(group.command, 'app-cell');
    addCell(group.fullCommand, 'path-cell');
    addCell(group.cwd, 'path-cell');
    addCell(group.displayPort);
    addCell(group.pid ?? '—');
    addCell(group.family);
    addCell(group.ppid ?? '—');
    addCell(group.user);

    const connectionsCell = document.createElement('td');
    const list = document.createElement('div');
    list.className = 'socket-list';

    group.sockets.forEach((socket) => {
      const socketRow = document.createElement('div');
      socketRow.className = 'socket-item';

      const protocolChip = document.createElement('span');
      protocolChip.className = 'chip protocol';
      protocolChip.textContent = socket.protocol || '—';
      socketRow.appendChild(protocolChip);

      const target = document.createElement('span');
      target.className = 'connection-target';
      target.textContent = `${socket.host}:${socket.port}`;
      socketRow.appendChild(target);

      const badge = document.createElement('span');
      badge.className = `badge ${stateClass(socket.state)}`;
      badge.textContent = formatState(socket.state);
      socketRow.appendChild(badge);

      if (socket.address && socket.address !== '—') {
        const address = document.createElement('span');
        address.className = 'connection-address';
        address.textContent = socket.address;
        socketRow.appendChild(address);
      }

      list.appendChild(socketRow);
    });

    connectionsCell.appendChild(list);
    row.appendChild(connectionsCell);

    const actionsCell = document.createElement('td');
    actionsCell.className = 'actions';

    const createButton = (label, className, force = false) => {
      const btn = document.createElement('button');
      btn.textContent = label;
      btn.className = className;
      btn.addEventListener('click', () => openKillDialog(group, force));
      return btn;
    };

    actionsCell.appendChild(createButton('Kill', 'kill'));
    actionsCell.appendChild(createButton('Force', 'force-kill', true));
    row.appendChild(actionsCell);

    tableBody.appendChild(row);
  });

  updateSortIndicator();
};

const fetchPorts = async () => {
  setStatus('Loading occupied ports…', 'info');
  tableBody.innerHTML = `
    <tr>
      <td colspan="10" class="empty">Loading…</td>
    </tr>`;
  try {
    const response = await fetch('/api/ports');
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || 'Failed to load port data');
    }
    const ports = payload.ports || [];
    renderRows(ports);
    const timestamp = new Date().toLocaleTimeString();
    lastUpdated.textContent = `Updated ${timestamp}`;
    const socketCount = payload.count ?? ports.length;
    const processCount = new Set(ports.map((entry) => entry.pid)).size;
    setStatus(`Showing ${processCount} process(es) across ${socketCount} sockets.`, 'success');
  } catch (error) {
    setStatus(error.message, 'error');
  }
};

refreshBtn.addEventListener('click', fetchPorts);

if (portHeader) {
  portHeader.addEventListener('click', () => {
    sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
    renderRows(cachedPorts);
  });
  updateSortIndicator();
}

confirmCancel?.addEventListener('click', () => closeKillDialog());
confirmModal?.addEventListener('click', (event) => {
  if (event.target === confirmModal) {
    closeKillDialog();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && confirmModal && !confirmModal.classList.contains('hidden')) {
    closeKillDialog();
  }
});

confirmAccept?.addEventListener('click', () => {
  if (!pendingKill) return;
  const { pid, force } = pendingKill;
  closeKillDialog();
  triggerKill(pid, force);
});

fetchPorts();
