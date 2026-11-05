"""Keep a packaged Qt application's libraries out of external scanner runtimes."""
import os
import sys
import subprocess


def no_console_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def external_environment():
    environment = os.environ.copy()
    if getattr(sys, "frozen", False):
        for name in ("LD_LIBRARY_PATH", "LIBPATH"):
            original = environment.get(name + "_ORIG")
            if original is not None:
                environment[name] = original
            else:
                environment.pop(name, None)
    return environment
