"""Run the local UI and weather servers together; Ctrl+C stops both.

WHY THIS FILE EXISTS
--------------------
Without this launcher, you must open two terminals, start two servers, and
remember to stop both. This file manages their lifetimes from one terminal.
It does not replace either server or implement their HTTP routes.

There are three Python processes while this launcher is running:

    run_servers.py          parent: starts, watches, and stops the children
        tool_server/app.py child: serves weather tool requests on port 5000
        Flask UI           child: serves the browser on port 8000 by default

A process is a running program with its own memory and execution state.
The agent loop runs inside the UI process, not in a fourth process.
Groq and OpenWeatherMap are services elsewhere, not processes we start here.

STARTUP AND SHUTDOWN AT A GLANCE
------------------------------
1. Read --ui-port and reject invalid values.
2. Register handlers for shutdown signals such as Ctrl+C.
3. Check that neither server's port is already occupied.
4. Check that secrets.json contains both API keys.
5. Start both children without waiting for either to finish.
6. Watch for a shutdown request or a child that has exited.
7. Stop and collect the children before leaving the launcher.

Examples, from the agent-lesson directory:
    python run_servers.py
    python run_servers.py --ui-port 8001

These are local development servers, not a production hosting setup.
"""

# All of these imports are from Python's standard library. We do not need an
# extra process-management dependency for this small two-server launcher.

# Turns command-line text such as "--ui-port 8001" into usable Python values.
import argparse

# Lets this process respond to operating-system notifications, including Ctrl+C.
import signal

# Gives access to low-level network endpoints. Here we only use a temporary
# socket to check whether a local TCP port can be reserved.
import socket

# Starts other programs and gives us handles for checking and stopping them.
import subprocess

# Provides the current Python executable, platform name, and error output stream.
import sys

# We use an Event as a shutdown flag. No worker thread is created by this file.
import threading

# Handles filesystem paths without manually joining Windows or Unix separators.
from pathlib import Path

# Our project's helper reads API keys from JSON without using environment variables.
from config import load_secrets

# __file__ is the path of THIS file, not the folder your terminal happens to be in.
# resolve() makes it absolute and resolves symbolic links; parent gets its folder.
# We use this as each child's working directory so relative paths such as
# "tool_server/app.py" work even when you launch from the workspace folder above.
PROJECT_ROOT = Path(__file__).resolve().parent


def check_ports(ui_port: int) -> None:
    """Check the weather and UI ports before starting either child.

    ui_port is the chosen browser-facing port; the weather port is fixed at 5000
    because agent/tools.py sends its HTTP requests there.
    Returns None on success. Raises OSError when a port cannot be reserved.
    """
    # An IP address identifies a network interface; a port identifies an endpoint
    # at that address. These two servers need different ports on the same machine.
    # 127.0.0.1 is the loopback address: it means THIS computer, not another device.
    for port in (5000, ui_port):
        # A socket is an operating-system-managed network endpoint. The defaults
        # here are IPv4 and a TCP stream, matching our servers' local HTTP setup.
        # Creating a socket does NOT yet connect to anything or start a server.
        #
        # "with" closes this temporary socket whether bind succeeds or raises.
        # Otherwise the check itself could hold the port and block the real server.
        with socket.socket() as listener:
            # "win32" is Python's platform name for Windows, including 64-bit Windows.
            if sys.platform == "win32":
                # Windows has a socket option for exclusive address ownership.
                # Without it, Windows address-sharing behavior can make a simple
                # bind check less reliable when another socket allows sharing.
                # SOL_SOCKET selects socket-level settings; the final 1 enables
                # SO_EXCLUSIVEADDRUSE. This Windows-specific option is not used
                # on other operating systems.
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                # bind asks the OS: "Can I reserve this exact address and port?"
                # This is a better check than sending an HTTP request: a port may
                # be occupied even if its program does not serve valid HTTP.
                # We never call listen() or accept(), so this is NOT a third server.
                listener.bind(("127.0.0.1", port))
            except OSError as error:
                # Translate the OS error into a useful startup message. The usual
                # cause is another server, though permissions or another OS-level
                # restriction can also prevent binding.
                # "from error" preserves the original cause for debugging.
                raise OSError(
                    f"Port {port} is already in use. Stop the existing server first."
                ) from error
    # Both temporary sockets are now closed. This is an early conflict check,
    # not a permanent reservation: another program could take a port before our
    # children bind it. The child-exit monitor below handles that startup failure.


def stop_servers(processes: list[subprocess.Popen]) -> None:
    """Stop the child processes recorded by this launcher.

    processes contains Popen handles, not server names or port numbers.
    Returns None. Each child gets up to five seconds to exit after termination,
    followed by a kill and another bounded wait if needed.
    OS errors or a timeout after the kill can still propagate to the caller.
    """
    # Only touch processes we started. Searching for and killing everything on
    # a port could accidentally terminate somebody else's application.
    # First request termination for ALL running children, then wait for them in
    # a separate loop, so one slow child does not delay stopping the other.
    for process in processes:
        # poll() checks immediately; it does not wait.
        # None means "still running". An integer means "already exited".
        if process.poll() is None:
            # On Windows this uses TerminateProcess, which is abrupt. On Unix it
            # sends SIGTERM. It is not an HTTP shutdown request and does not
            # guarantee the child will finish active requests or run its finally
            # blocks. That tradeoff keeps this development launcher small.
            process.terminate()
    for process in processes:
        try:
            # wait() collects the exit status and waits for OS-level process exit.
            # A timeout prevents a stuck child from blocking this step forever.
            # It also works for a child that has already exited.
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Escalate if termination did not finish in time. On Unix kill() uses
            # SIGKILL; on Windows kill() and terminate() both use TerminateProcess.
            process.kill()
            process.wait(timeout=5)


def run_servers(ui_port: int, stopped: threading.Event) -> int:
    """Start both servers and supervise them until signalled or a child exits.

    ui_port is the validated UI port. stopped is an Event whose set state means
    that shutdown has been requested by a signal handler in main().
    Returns zero for a requested shutdown and one for startup or child failure.
    Cleanup is attempted for all recorded children in the finally block.
    Unhandled exceptions propagate after that cleanup attempt.
    """
    # We append a handle immediately after each successful launch. If the second
    # launch fails, the first child is still in this list and can be cleaned up.
    processes = []

    # Each inner list is ONE program invocation. Each element is ONE argument.
    # Popen uses shell=False by default: these are not PowerShell commands.
    # Argument lists avoid nested shell quoting problems, especially on Windows.
    # sys.executable chooses the Python running THIS launcher, preserving its
    # virtual environment instead of hoping that "python" on PATH is the same.
    commands = [
        # Equivalent to: <current Python> tool_server/app.py
        # That script binds to 127.0.0.1:5000; its weather client reads JSON keys.
        [sys.executable, "tool_server/app.py"],
        # Equivalent to running Flask's command-line interface with this Python:
        #   -m flask              run the installed flask module
        #   --app ui_server.app   import app from ui_server/app.py
        #   run                   start Flask's development HTTP server
        #   --host 127.0.0.1       accept local connections only
        #   --port <ui_port>      use the port chosen on our command line
        #   --no-reload           do not create a reloader process
        #
        # Running ui_server/app.py directly uses its hard-coded port 8000.
        # Flask's CLI lets us choose a port without changing that server file.
        # Disabling reload also keeps each child handle tied to the actual server
        # process instead of supervising a reloader that spawns another process.
        [sys.executable, "-m", "flask", "--app", "ui_server.app", "run",
         "--host", "127.0.0.1", "--port", str(ui_port), "--no-reload"],
    ]
    try:
        # Do this before launching either child to avoid a half-started setup
        # when a known port conflict already exists.
        check_ports(ui_port)

        # Validate the JSON file before starting either server. Each API client
        # reads its key directly from that file when making a request.
        # Keys are not stored in environment variables or printed here.
        load_secrets()
        for command in commands:
            # Popen starts a child and returns WITHOUT waiting for it to finish.
            # subprocess.run() would wait, so the first server would prevent us
            # from ever reaching the second launch.
            #
            # cwd sets the child's working directory, not the parent's directory.
            # We leave stdout/stderr alone so both servers write to this terminal.
            # Their log lines can interleave because they run independently.
            #
            # On Windows, a new process group prevents the console's ordinary
            # Ctrl+C event from independently interrupting these children. The
            # launcher receives Ctrl+C and controls their shutdown instead.
            # Other platforms use creationflags=0 (no Windows-specific flags).
            processes.append(subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            ))
        # flush=True displays the message immediately even if output is buffered.
        # This announces the intended URLs, not a readiness/health check: the
        # children may still be importing modules and opening their ports.
        print(f"UI: http://127.0.0.1:{ui_port}\nWeather tool: http://127.0.0.1:5000\n"
              "Press Ctrl+C to stop both servers.", flush=True)

        # Event.wait(0.25) pauses for at most a quarter second. It returns True
        # immediately when the Event is set, or False when the timeout expires.
        # "not" keeps the loop running only while shutdown has NOT been requested.
        #
        # This avoids a busy loop that would continuously check processes and
        # waste CPU. The timeout also lets us notice a child exit about four
        # times per second while still waking promptly for a shutdown request.
        while not stopped.wait(0.25):
            # any(...) is True if at least one child has exited. Use "is not None"
            # rather than checking truthiness: exit code 0 also means it exited.
            # Even a successful exit is unexpected here because both programs
            # are supposed to keep serving requests until we stop the launcher.
            if any(process.poll() is not None for process in processes):
                print("A server exited. Stopping both servers.", file=sys.stderr)
                # A return inside try STILL executes finally before leaving.
                return 1
        # The Event was set. This is the normal, requested shutdown path.
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        # Handle expected OS/startup errors without leaving a child behind.
        # stderr is the conventional stream for error messages.
        # RuntimeError includes missing or malformed secrets configuration.
        print(f"Could not start servers: {error}", file=sys.stderr)
        return 1
    finally:
        # Runs after normal shutdown, early return, or an exception in try.
        # If nothing started, processes is empty and cleanup has nothing to do.
        # If only one child started, that child is still stopped.
        #
        # "finally" cannot protect against forcibly killing the launcher itself,
        # a machine crash, or loss of power. Ctrl+C is the intended stop method.
        stop_servers(processes)


def main() -> int:
    """Read command-line options, install shutdown handlers, and run the supervisor.

    Returns the supervisor's exit code. argparse exits early for --help or
    invalid arguments instead of starting any children.
    """
    # __doc__ is this module's opening docstring; argparse displays it as help.
    # It also automatically adds --help and reports invalid command-line syntax.
    parser = argparse.ArgumentParser(description=__doc__)

    # Optional flag: no flag means 8000; "--ui-port 8001" chooses 8001 instead.
    # type=int converts the user's text and rejects values such as "banana".
    parser.add_argument("--ui-port", type=int, default=8000)
    args = parser.parse_args()

    # TCP port numbers end at 65535. We intentionally limit this UI to the
    # non-privileged range starting at 1024 for portable development defaults.
    # 5000 is excluded because our weather server already needs that port.
    # parser.error prints a helpful error and exits with code 2.
    if not 1024 <= args.ui_port <= 65535 or args.ui_port == 5000:
        parser.error("--ui-port must be 1024-65535 and different from 5000")

    # Think of Event as a switch, initially OFF. set() turns it ON and wakes
    # anyone waiting on it. We never clear it: one shutdown request is enough.
    # threading.Event is useful even here without starting any threads, because
    # it combines a flag with an interruptible, low-CPU wait.
    stopped = threading.Event()

    # A signal is an OS notification delivered to this process:
    # SIGINT  normally comes from Ctrl+C.
    # SIGTERM is a conventional termination request, mainly on Unix-like systems.
    # Registering SIGTERM does not make Windows TerminateProcess graceful.
    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        # signal.signal(number, handler) registers a function for that signal.
        # Python calls the handler with (signal_number, current_stack_frame).
        # "lambda *_" accepts and ignores both arguments; its only job is set().
        #
        # Keep the handler small: it requests shutdown rather than stopping
        # processes itself. run_servers then leaves its loop and runs finally.
        signal.signal(shutdown_signal, lambda *_: stopped.set())

    # Windows also has Ctrl+Break, represented by SIGBREAK. hasattr guards this
    # because Unix-like platforms do not necessarily define that signal.
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda *_: stopped.set())

    # All helpers are now defined, arguments are valid, and handlers are ready.
    # This call performs the actual startup and stays active until shutdown.
    return run_servers(args.ui_port, stopped)


# Python sets __name__ to "__main__" when you execute this file as a script.
# When a test imports run_servers, __name__ is "run_servers" instead, so importing
# definitions does not accidentally start servers or register signal handlers.
if __name__ == "__main__":
    # main() returns a number; SystemExit passes that number to the OS as the
    # program's exit status. 0 conventionally means success; nonzero means failure.
    # This line is an exit request, not an additional server or process launch.
    raise SystemExit(main())