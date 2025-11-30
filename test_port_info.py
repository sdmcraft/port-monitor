"""
Comprehensive tests for port_info module.

Tests all port information collection, process detail retrieval,
and process management functionality.
"""

import subprocess
from unittest.mock import patch, Mock, MagicMock
import pytest

from port_info import (
    PortFetchError,
    _get_lsof_path,
    _split_host_port,
    _parse_lsof_output,
    collect_ports,
    _get_process_field,
    _get_process_command,
    _get_parent_pid,
    _get_process_cwd,
    _get_process_details,
    kill_process,
)


class TestGetLsofPath:
    """Tests for _get_lsof_path function."""

    def test_lsof_found(self):
        """Test when lsof is found in PATH."""
        with patch("port_info.shutil.which", return_value="/usr/sbin/lsof"):
            result = _get_lsof_path()
            assert result == "/usr/sbin/lsof"

    def test_lsof_not_found(self):
        """Test when lsof is not found in PATH."""
        with patch("port_info.shutil.which", return_value=None):
            with pytest.raises(PortFetchError, match="lsof.*required.*not found"):
                _get_lsof_path()


class TestSplitHostPort:
    """Tests for _split_host_port function."""

    def test_ipv4_with_port(self):
        """Test parsing IPv4 address with port."""
        host, port = _split_host_port("127.0.0.1:8080")
        assert host == "127.0.0.1"
        assert port == "8080"

    def test_ipv6_with_port(self):
        """Test parsing IPv6 address with port."""
        host, port = _split_host_port("[::1]:8080")
        assert host == "::1"
        assert port == "8080"

    def test_ipv6_without_port(self):
        """Test parsing IPv6 address without port."""
        host, port = _split_host_port("[::1]")
        assert host == "::1"
        assert port == ""

    def test_connection_state(self):
        """Test parsing address with connection state (->)."""
        host, port = _split_host_port("127.0.0.1:8080->192.168.1.1:443")
        assert host == "127.0.0.1"
        assert port == "8080"

    def test_hostname_only(self):
        """Test parsing hostname without port."""
        host, port = _split_host_port("localhost")
        assert host == "localhost"
        assert port == ""

    def test_wildcard(self):
        """Test parsing wildcard address."""
        host, port = _split_host_port("*:*")
        assert host == "*"
        assert port == "*"

    def test_empty_address(self):
        """Test parsing empty address."""
        host, port = _split_host_port("")
        assert host == ""
        assert port == ""

    def test_ipv4_without_port(self):
        """Test parsing IPv4 address without port."""
        host, port = _split_host_port("192.168.1.1")
        assert host == "192.168.1.1"
        assert port == ""


class TestParseLsofOutput:
    """Tests for _parse_lsof_output function."""

    @patch("port_info._get_process_details")
    def test_parse_valid_output(self, mock_get_details):
        """Test parsing valid lsof output."""
        mock_get_details.return_value = {
            "ppid": 1,
            "command_path": "/usr/bin/python3",
            "cwd": "/home/user",
        }

        output = """COMMAND     PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
python3    1234   user   3u  IPv4 0x1234567890abcdef      0t0  TCP *:8080 (LISTEN)"""

        result = _parse_lsof_output(output)

        assert len(result) == 1
        entry = result[0]
        assert entry["command"] == "python3"
        assert entry["pid"] == 1234
        assert entry["user"] == "user"
        assert entry["port"] == "8080"
        assert entry["protocol"] == "TCP"
        assert entry["state"] == "LISTEN"
        assert entry["ppid"] == 1
        assert entry["full_command"] == "/usr/bin/python3"
        assert entry["cwd"] == "/home/user"

    def test_parse_empty_output(self):
        """Test parsing empty lsof output."""
        result = _parse_lsof_output("")
        assert result == []

    def test_parse_header_only(self):
        """Test parsing output with only header."""
        output = "COMMAND     PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME"
        result = _parse_lsof_output(output)
        assert result == []

    @patch("port_info._get_process_details")
    def test_parse_malformed_line(self, mock_get_details):
        """Test parsing output with malformed lines."""
        mock_get_details.return_value = {
            "ppid": None,
            "command_path": "",
            "cwd": "",
        }

        output = """COMMAND     PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
python3    1234   user"""  # Incomplete line

        result = _parse_lsof_output(output)
        assert result == []

    @patch("port_info._get_process_details")
    def test_parse_invalid_pid(self, mock_get_details):
        """Test parsing output with invalid PID."""
        output = """COMMAND     PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
python3    INVALID   user   3u  IPv4 0x1234567890abcdef      0t0  TCP *:8080 (LISTEN)"""

        result = _parse_lsof_output(output)
        assert result == []

    @patch("port_info._get_process_details")
    def test_parse_ipv6_address(self, mock_get_details):
        """Test parsing output with IPv6 address."""
        mock_get_details.return_value = {
            "ppid": 1,
            "command_path": "/usr/bin/node",
            "cwd": "/app",
        }

        output = """COMMAND     PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
node       5678   user   4u  IPv6 0xabcdef1234567890      0t0  TCP [::1]:3000 (LISTEN)"""

        result = _parse_lsof_output(output)

        assert len(result) == 1
        entry = result[0]
        assert entry["host"] == "::1"
        assert entry["port"] == "3000"
        assert entry["type"] == "IPv6"


class TestCollectPorts:
    """Tests for collect_ports function."""

    @patch("port_info._get_lsof_path")
    @patch("port_info.subprocess.run")
    @patch("port_info._parse_lsof_output")
    def test_collect_ports_success(self, mock_parse, mock_run, mock_lsof_path):
        """Test successful port collection."""
        mock_lsof_path.return_value = "/usr/sbin/lsof"
        mock_result = Mock()
        mock_result.stdout = "lsof output"
        mock_run.return_value = mock_result
        mock_parse.return_value = [{"port": "8080"}]

        result = collect_ports()

        assert result == [{"port": "8080"}]
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["/usr/sbin/lsof", "-nP", "-iTCP", "-iUDP"]

    @patch("port_info._get_lsof_path")
    @patch("port_info.subprocess.run")
    def test_collect_ports_command_fails(self, mock_run, mock_lsof_path):
        """Test port collection when lsof command fails."""
        mock_lsof_path.return_value = "/usr/sbin/lsof"
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "lsof", stderr="permission denied"
        )

        with pytest.raises(PortFetchError, match="permission denied"):
            collect_ports()

    @patch("port_info._get_lsof_path")
    def test_collect_ports_lsof_not_found(self, mock_lsof_path):
        """Test port collection when lsof is not found."""
        mock_lsof_path.side_effect = PortFetchError("lsof not found")

        with pytest.raises(PortFetchError, match="lsof not found"):
            collect_ports()


class TestGetProcessField:
    """Tests for _get_process_field function."""

    @patch("port_info.subprocess.run")
    def test_get_process_field_success(self, mock_run):
        """Test successful process field retrieval."""
        mock_result = Mock()
        mock_result.stdout = "/usr/bin/python3\n"
        mock_run.return_value = mock_result

        result = _get_process_field(1234, "command=")

        assert result == "/usr/bin/python3"
        mock_run.assert_called_once_with(
            ["ps", "-p", "1234", "-o", "command="],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @patch("port_info.subprocess.run")
    def test_get_process_field_not_found(self, mock_run):
        """Test process field retrieval when process not found."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "ps")

        result = _get_process_field(99999, "command=")

        assert result == ""

    @patch("port_info.subprocess.run")
    def test_get_process_field_caching(self, mock_run):
        """Test that process field results are cached."""
        mock_result = Mock()
        mock_result.stdout = "test\n"
        mock_run.return_value = mock_result

        # Clear cache first
        _get_process_field.cache_clear()

        # First call
        result1 = _get_process_field(1234, "command=")
        # Second call with same arguments
        result2 = _get_process_field(1234, "command=")

        assert result1 == result2 == "test"
        # Should only call subprocess once due to caching
        assert mock_run.call_count == 1


class TestGetProcessCommand:
    """Tests for _get_process_command function."""

    @patch("port_info._get_process_field")
    def test_get_process_command(self, mock_get_field):
        """Test getting process command."""
        mock_get_field.return_value = "/usr/bin/python3 app.py"

        result = _get_process_command(1234)

        assert result == "/usr/bin/python3 app.py"
        mock_get_field.assert_called_once_with(1234, "command=")


class TestGetParentPid:
    """Tests for _get_parent_pid function."""

    @patch("port_info._get_process_field")
    def test_get_parent_pid_valid(self, mock_get_field):
        """Test getting valid parent PID."""
        mock_get_field.return_value = "123"

        result = _get_parent_pid(1234)

        assert result == 123
        mock_get_field.assert_called_once_with(1234, "ppid=")

    @patch("port_info._get_process_field")
    def test_get_parent_pid_invalid(self, mock_get_field):
        """Test getting parent PID when value is not a number."""
        mock_get_field.return_value = "N/A"

        result = _get_parent_pid(1234)

        assert result is None

    @patch("port_info._get_process_field")
    def test_get_parent_pid_empty(self, mock_get_field):
        """Test getting parent PID when value is empty."""
        mock_get_field.return_value = ""

        result = _get_parent_pid(1234)

        assert result is None


class TestGetProcessCwd:
    """Tests for _get_process_cwd function."""

    @patch("port_info._get_lsof_path")
    @patch("port_info.subprocess.run")
    def test_get_process_cwd_success(self, mock_run, mock_lsof_path):
        """Test successful CWD retrieval."""
        mock_lsof_path.return_value = "/usr/sbin/lsof"
        mock_result = Mock()
        mock_result.stdout = "p1234\nn/home/user/project\n"
        mock_run.return_value = mock_result

        result = _get_process_cwd(1234)

        assert result == "/home/user/project"

    @patch("port_info._get_lsof_path")
    @patch("port_info.subprocess.run")
    def test_get_process_cwd_not_found(self, mock_run, mock_lsof_path):
        """Test CWD retrieval when process not found."""
        mock_lsof_path.return_value = "/usr/sbin/lsof"
        mock_run.side_effect = subprocess.CalledProcessError(1, "lsof")

        result = _get_process_cwd(99999)

        assert result == ""

    @patch("port_info._get_lsof_path")
    @patch("port_info.subprocess.run")
    def test_get_process_cwd_no_cwd_line(self, mock_run, mock_lsof_path):
        """Test CWD retrieval when output has no 'n' line."""
        # Clear cache to ensure test isolation
        _get_process_cwd.cache_clear()

        mock_lsof_path.return_value = "/usr/sbin/lsof"
        mock_result = Mock()
        mock_result.stdout = "p1234\n"
        mock_run.return_value = mock_result

        result = _get_process_cwd(9999)  # Use different PID to avoid cache collision

        assert result == ""


class TestGetProcessDetails:
    """Tests for _get_process_details function."""

    @patch("port_info._get_process_cwd")
    @patch("port_info._get_process_command")
    @patch("port_info._get_parent_pid")
    def test_get_process_details(self, mock_ppid, mock_cmd, mock_cwd):
        """Test getting all process details."""
        mock_ppid.return_value = 1
        mock_cmd.return_value = "/usr/bin/python3"
        mock_cwd.return_value = "/home/user"

        result = _get_process_details(1234)

        assert result == {
            "ppid": 1,
            "command_path": "/usr/bin/python3",
            "cwd": "/home/user",
        }


class TestKillProcess:
    """Tests for kill_process function."""

    @patch("port_info.os.kill")
    def test_kill_process_success(self, mock_kill):
        """Test successful process kill."""
        mock_kill.return_value = None

        # Should not raise any exception
        kill_process(1234, 15)  # SIGTERM = 15

        mock_kill.assert_called_once_with(1234, 15)

    @patch("port_info.os.kill")
    def test_kill_process_not_found(self, mock_kill):
        """Test killing non-existent process."""
        mock_kill.side_effect = ProcessLookupError()

        with patch("port_info.abort") as mock_abort:
            kill_process(99999, 15)
            mock_abort.assert_called_once_with(404, description="Process 99999 was not found.")

    @patch("port_info.os.kill")
    def test_kill_process_permission_denied(self, mock_kill):
        """Test killing process without permission."""
        mock_kill.side_effect = PermissionError()

        with patch("port_info.abort") as mock_abort:
            kill_process(1, 15)
            mock_abort.assert_called_once_with(
                403, description="Insufficient permissions to signal process 1."
            )

    @patch("port_info.os.kill")
    def test_kill_process_other_error(self, mock_kill):
        """Test killing process with unexpected error."""
        mock_kill.side_effect = RuntimeError("Unexpected error")

        with patch("port_info.abort") as mock_abort:
            kill_process(1234, 15)
            mock_abort.assert_called_once_with(
                500, description="Failed to signal process 1234: Unexpected error"
            )


class TestIntegration:
    """Integration tests combining multiple functions."""

    @patch("port_info._get_lsof_path")
    @patch("port_info.subprocess.run")
    def test_full_port_collection_flow(self, mock_run, mock_lsof_path):
        """Test complete flow from lsof execution to parsed output."""
        mock_lsof_path.return_value = "/usr/sbin/lsof"

        # Mock lsof output
        lsof_output = """COMMAND     PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
python3    1234   user   3u  IPv4 0x1234567890abcdef      0t0  TCP *:8080 (LISTEN)
node       5678   user   4u  IPv6 0xabcdef1234567890      0t0  TCP [::1]:3000 (LISTEN)"""

        # Mock subprocess for lsof
        lsof_result = Mock()
        lsof_result.stdout = lsof_output

        # Mock subprocess for ps commands (multiple calls)
        ps_results = [
            Mock(stdout="123\n"),  # ppid for 1234
            Mock(stdout="/usr/bin/python3 app.py\n"),  # command for 1234
            Mock(stdout="456\n"),  # ppid for 5678
            Mock(stdout="/usr/bin/node server.js\n"),  # command for 5678
        ]

        # Mock subprocess for lsof cwd commands
        cwd_results = [
            Mock(stdout="p1234\nn/home/user/python-app\n"),  # cwd for 1234
            Mock(stdout="p5678\nn/home/user/node-app\n"),  # cwd for 5678
        ]

        all_results = [lsof_result] + ps_results + cwd_results
        mock_run.side_effect = all_results

        result = collect_ports()

        assert len(result) == 2

        # Check first entry (python)
        assert result[0]["command"] == "python3"
        assert result[0]["pid"] == 1234
        assert result[0]["port"] == "8080"

        # Check second entry (node)
        assert result[1]["command"] == "node"
        assert result[1]["pid"] == 5678
        assert result[1]["port"] == "3000"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
