# Test Suite Summary for port_info.py

## Coverage: 100%

All 35 tests passing with complete code coverage.

## Test Categories

### 1. Utility Functions (12 tests)
- **_get_lsof_path**: Tests lsof discovery and error handling
- **_split_host_port**: Tests IPv4, IPv6, connection states, edge cases
  - IPv4 with/without port
  - IPv6 bracketed notation
  - Connection states (->)
  - Wildcards and empty strings

### 2. lsof Output Parsing (6 tests)
- **_parse_lsof_output**: Tests parsing various lsof formats
  - Valid multi-line output
  - Empty output
  - Malformed lines
  - Invalid PIDs
  - IPv6 addresses

### 3. Port Collection (3 tests)
- **collect_ports**: Tests end-to-end port collection
  - Successful collection
  - Command failures
  - lsof not found

### 4. Process Information (12 tests)
- **_get_process_field**: Generic ps field retrieval with caching
- **_get_process_command**: Command path retrieval
- **_get_parent_pid**: PPID retrieval with validation
- **_get_process_cwd**: Working directory retrieval
- **_get_process_details**: Consolidated process information

### 5. Process Management (4 tests)
- **kill_process**: Tests signal sending
  - Successful kill
  - Process not found (404)
  - Permission denied (403)
  - Unexpected errors (500)

### 6. Integration Tests (1 test)
- Full flow from lsof execution to parsed output
- Tests multiple processes with different protocols

## Running Tests

```bash
# Run all tests
python -m pytest test_port_info.py -v

# Run with coverage
python -m pytest test_port_info.py --cov=port_info --cov-report=term-missing

# Run specific test class
python -m pytest test_port_info.py::TestKillProcess -v

# Run specific test
python -m pytest test_port_info.py::TestKillProcess::test_kill_process_success -v
```

## Regression Protection

These tests will catch regressions in:
- Address parsing logic (IPv4/IPv6)
- lsof output format changes
- Process information retrieval
- Error handling and HTTP status codes
- Caching behavior
- Signal sending functionality

## Test Design Features

- **Mocking**: All external dependencies (subprocess, os.kill, shutil.which) are mocked
- **Isolation**: Tests are independent and don't affect each other
- **Cache Management**: Proper cache clearing for cached functions
- **Edge Cases**: Tests cover error conditions, empty inputs, malformed data
- **Integration**: Full end-to-end flow testing
