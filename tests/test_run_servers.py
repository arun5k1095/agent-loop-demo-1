import threading
import unittest
from unittest.mock import Mock, patch

import run_servers


class RunServersTests(unittest.TestCase):
    def test_requested_shutdown_stops_both_children(self):
        stopped = threading.Event()
        stopped.set()
        children = [Mock(), Mock()]
        for child in children:
            child.poll.return_value = None
        with patch.object(run_servers, "check_ports"), patch.object(
            run_servers, "load_secrets"
        ), patch.object(run_servers.subprocess, "Popen", side_effect=children) as launch:
            self.assertEqual(run_servers.run_servers(8001, stopped), 0)
        self.assertEqual(launch.call_count, 2)
        self.assertEqual(launch.call_args_list[0].args[0][0], run_servers.sys.executable)
        self.assertIn("8001", launch.call_args_list[1].args[0])
        for child in children:
            child.terminate.assert_called_once()
            child.wait.assert_called_once_with(timeout=5)

    def test_second_launch_failure_stops_first_child(self):
        child = Mock()
        child.poll.return_value = None
        with patch.object(run_servers, "check_ports"), patch.object(
            run_servers, "load_secrets"
        ), patch.object(run_servers.subprocess, "Popen", side_effect=[child, OSError("failed")]):
            self.assertEqual(run_servers.run_servers(8001, threading.Event()), 1)
        child.terminate.assert_called_once()

    def test_occupied_port_does_not_launch_any_children(self):
        with patch.object(run_servers, "check_ports", side_effect=OSError("occupied")), patch.object(
            run_servers.subprocess, "Popen"
        ) as launch:
            self.assertEqual(run_servers.run_servers(8001, threading.Event()), 1)
        launch.assert_not_called()

    def test_child_exit_stops_remaining_server(self):
        stopped = Mock()
        stopped.wait.return_value = False
        exited, running = Mock(), Mock()
        exited.poll.return_value = 1
        running.poll.return_value = None
        with patch.object(run_servers, "check_ports"), patch.object(
            run_servers, "load_secrets"
        ), patch.object(run_servers.subprocess, "Popen", side_effect=[exited, running]):
            self.assertEqual(run_servers.run_servers(8001, stopped), 1)
        running.terminate.assert_called_once()

    def test_unresponsive_child_is_killed(self):
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [run_servers.subprocess.TimeoutExpired("server", 5), 0]
        run_servers.stop_servers([child])
        child.kill.assert_called_once()