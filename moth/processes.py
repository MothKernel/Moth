"""Keep a packaged Qt application's libraries out of external scanner runtimes."""
import os
import sys
import subprocess


def no_console_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def external_environment():
    environment = os.environ.copy()
    if sys.platform == 'darwin':
        # Finder launches do not inherit the user's interactive shell PATH.
        paths = environment.get('PATH', '').split(os.pathsep)
        for folder in ('/opt/homebrew/bin', '/usr/local/bin', '/opt/local/bin'):
            if folder not in paths:
                paths.append(folder)
        environment['PATH'] = os.pathsep.join(filter(None, paths))
    if getattr(sys, "frozen", False):
        for name in ("LD_LIBRARY_PATH", "LIBPATH"):
            original = environment.get(name + "_ORIG")
            if original is not None:
                environment[name] = original
            else:
                environment.pop(name, None)
    return environment
