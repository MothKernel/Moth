"""Per-tool prerequisites using official installers and native package managers.

Runs in the existing installation queue, never on the Qt thread. Native dialogs
handle elevation and licenses; Moth never collects an administrator password.
"""
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote
from .processes import external_environment, no_console_flags


class ActionRequired(ValueError):
    def __init__(self, key):
        self.key = key
        super().__init__(key)


def run(args, timeout=1800, acceptable_codes=(0,)):
    from .tools import run_install
    return run_install([str(arg) for arg in args], timeout=timeout, acceptable_codes=acceptable_codes)


def capture(args, timeout=20):
    return subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout,
                          env=external_environment(), creationflags=no_console_flags())


def progress(tool, key):
    from . import tools
    with tools.LOCK:
        tools.STATE.setdefault(tool, {}).update(message_key=key, message='')


def docker_command():
    from .tools import executable_candidates
    found = next(executable_candidates('docker'), None)
    if found:
        return str(found)
    candidates = [Path('/Applications/Docker.app/Contents/Resources/bin/docker'),
                  Path.home() / 'Applications/Docker.app/Contents/Resources/bin/docker']
    if sys_platform() == 'win32':
        candidates += [Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Docker/Docker/resources/bin/docker.exe',
                       Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/DockerDesktop/resources/bin/docker.exe']
    return next((str(p) for p in candidates if p.is_file()), None)


def sys_platform():
    import sys
    return sys.platform


def windows_installer(path, arguments=''):
    # PowerShell string literals escape apostrophes by doubling them. No user
    # input is interpolated as PowerShell code; paths come from our temp folder.
    literal = "'" + str(path).replace("'", "''") + "'"
    script = "$ErrorActionPreference='Stop'; $p=Start-Process -FilePath " + literal
    if arguments:
        script += " -ArgumentList '" + arguments.replace("'", "''") + "'"
    script += ' -Verb RunAs -Wait -PassThru; exit $p.ExitCode'
    code = run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], acceptable_codes=(0, 3010, 1641))
    if code in (3010, 1641):
        raise ActionRequired('setup_restart')


def verified_download(url, name, checksum_url, folder, nmap=False):
    from .tools import download, verify_checksum
    archive, checksums = folder / name, folder / 'checksums.txt'
    download(checksum_url, checksums, 2_000_000)
    if nmap:
        match = re.search(r'^SHA256\s*=\s*([A-Fa-f0-9 ]+)\s*$', checksums.read_text(), re.M)
        digest = re.sub(r'\s', '', match[1]) if match else ''
        if not re.fullmatch(r'[a-fA-F0-9]{64}', digest):
            raise ValueError('The official installer has no valid SHA-256 digest. Installation refused.')
        checksums.write_text(digest + '  ' + name + '\n')
    # Docker Desktop images can exceed one GB. Same bounded streaming downloader.
    download(url, archive, 2_500_000_000)
    verify_checksum(archive, checksums)
    return archive


def official_nmap(folder, suffix):
    from .tools import download
    page = folder / 'download.html'
    download('https://nmap.org/download.html', page, 2_000_000)
    match = re.search(r'https://nmap\.org/dist/(nmap-[0-9]+\.[0-9]+(?:\.[0-9]+)?' + re.escape(suffix) + ')', page.read_text())
    if not match:
        raise ValueError('No compatible official Nmap installer was found. Use nmap.org/download.html.')
    return verified_download(match[0], match[1], 'https://nmap.org/dist/sigs/' + match[1] + '.digest.txt', folder, nmap=True)


def docker_download(folder, system):
    machine = platform.machine().lower()
    if machine not in ('arm64', 'aarch64', 'amd64', 'x86_64'):
        raise ActionRequired('setup_unsupported')
    arch = 'arm64' if machine in ('arm64', 'aarch64') else 'amd64'
    name = 'Docker Desktop Installer.exe' if system == 'win32' else 'Docker.dmg'
    base = f'https://desktop.docker.com/{"win" if system == "win32" else "mac"}/main/{arch}/'
    return verified_download(base + quote(name), name, base + 'checksums.txt', folder)


def mac_dmg(path, docker=False):
    with tempfile.TemporaryDirectory(prefix='moth-mount-') as mount:
        run(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, path])
        try:
            if docker:
                app = Path(mount) / 'Docker.app'
                run(['/usr/sbin/spctl', '--assess', '--type', 'execute', app], timeout=120)
                destination = Path('/Applications/Docker.app')
                if destination.exists():
                    raise ActionRequired('setup_docker_start')
                args = ['/usr/bin/ditto', str(app), str(destination)]
                if os.access('/Applications', os.W_OK):
                    run(args)
                else:
                    command = shlex.join(args)
                    script = 'do shell script ' + apple_string(command) + ' with administrator privileges'
                    run(['/usr/bin/osascript', '-e', script])
            else:
                packages = sorted(Path(mount).glob('*.mpkg')) + sorted(Path(mount).glob('*.pkg'))
                if not packages:
                    raise ValueError('The official Nmap disk image contains no installer package.')
                run(['/usr/bin/open', '-W', '-a', 'Installer', packages[0]])
        finally:
            run(['/usr/bin/hdiutil', 'detach', mount], timeout=30)


def apple_string(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def linux_package_command(tool, release=None):
    release = platform.freedesktop_os_release() if release is None else release
    ids = [release.get('ID', '')] + release.get('ID_LIKE', '').split()
    if any(name in ids for name in ('arch', 'manjaro')):
        return ['pacman', '-S', '--needed', '--noconfirm', 'docker' if tool == 'zap' else 'nmap']
    if any(name in ids for name in ('debian', 'ubuntu')):
        return ['apt-get', 'install', '-y', 'docker.io' if tool == 'zap' else 'nmap']
    if 'fedora' in ids:
        return ['dnf', 'install', '-y', 'moby-engine' if tool == 'zap' else 'nmap']
    if any(name in ids for name in ('opensuse', 'opensuse-leap', 'opensuse-tumbleweed', 'suse')):
        return ['zypper', '--non-interactive', 'install', 'docker' if tool == 'zap' else 'nmap']
    raise ActionRequired('setup_unsupported')


def privileged(args):
    binary = shutil.which(args[0])
    if not binary:
        raise ActionRequired('setup_unsupported')
    command = [binary] + args[1:]
    if os.geteuid() == 0:
        run(command)
    else:
        pkexec = shutil.which('pkexec')
        if not pkexec:
            raise ActionRequired('setup_polkit')
        run([pkexec] + command)


def ensure_linux_docker_access(docker):
    privileged(['systemctl', 'start', 'docker'])
    result = capture([docker, 'info', '--format', '{{.OSType}}'])
    if result.returncode == 0:
        return
    output = (result.stdout + result.stderr).decode(errors='replace').lower()
    if 'permission denied' in output:
        import pwd
        user = pwd.getpwuid(os.getuid()).pw_name
        privileged(['usermod', '-aG', 'docker', user])
        raise ActionRequired('setup_login')
    raise ActionRequired('setup_docker_start')


def start_desktop(system):
    if system == 'darwin':
        apps = [Path('/Applications/Docker.app'), Path.home() / 'Applications/Docker.app']
        app = next((p for p in apps if p.exists()), None)
        if app:
            run(['/usr/bin/open', app], timeout=30)
    elif system == 'win32':
        roots = [Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Docker/Docker',
                 Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/DockerDesktop']
        app = next((p / 'Docker Desktop.exe' for p in roots if (p / 'Docker Desktop.exe').is_file()), None)
        if app:
            subprocess.Popen([str(app)], env=external_environment(), creationflags=no_console_flags())


def prepare_docker(report_tool='docker'):
    system = sys_platform()
    docker = docker_command()
    if docker:
        try:
            ready = capture([docker, 'info', '--format', '{{.OSType}}'])
            if ready.returncode == 0 and ready.stdout.strip() == b'linux':
                return docker
        except (OSError, subprocess.TimeoutExpired):
            pass
    progress(report_tool, 'setup_docker_install' if not docker else 'setup_docker_starting')
    if not docker:
        if system in ('win32', 'darwin'):
            with tempfile.TemporaryDirectory(prefix='moth-docker-') as temp:
                installer = docker_download(Path(temp), system)
                if system == 'win32':
                    windows_installer(installer, 'install')
                else:
                    mac_dmg(installer, docker=True)
        elif system.startswith('linux'):
            privileged(linux_package_command('zap'))
        else:
            raise ActionRequired('setup_unsupported')
        docker = docker_command()
        if not docker:
            raise ActionRequired('setup_docker_start')
    if system.startswith('linux'):
        ensure_linux_docker_access(docker)
    else:
        start_desktop(system)
    progress(report_tool, 'setup_docker_wait')
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            result = capture([docker, 'info', '--format', '{{.OSType}}'], timeout=8)
            if result.returncode == 0:
                if result.stdout.strip() != b'linux':
                    raise ActionRequired('setup_linux_containers')
                return docker
        except (OSError, subprocess.TimeoutExpired):
            pass
        time.sleep(2)
    raise ActionRequired('setup_docker_start')


def ensure_docker():
    """ZAP may start an existing engine, but never installs a missing dependency."""
    if not docker_command():
        raise ActionRequired('setup_docker_missing')
    return prepare_docker('zap')


def install_nmap():
    system = sys_platform()
    progress('nmap', 'setup_nmap_install')
    if system == 'win32':
        with tempfile.TemporaryDirectory(prefix='moth-nmap-') as temp:
            windows_installer(official_nmap(Path(temp), '-setup.exe'))
    elif system == 'darwin':
        from .tools import executable_candidates
        brew = next(executable_candidates('brew'), None)
        if brew:
            run([brew, 'install', 'nmap'])
        else:
            with tempfile.TemporaryDirectory(prefix='moth-nmap-') as temp:
                mac_dmg(official_nmap(Path(temp), '.dmg'))
    elif system.startswith('linux'):
        privileged(linux_package_command('nmap'))
    else:
        raise ActionRequired('setup_unsupported')
    from .tools import command
    if not command('nmap'):
        raise ActionRequired('setup_nmap_missing')


DEPENDENCIES = [
    dict(id='docker', name='Docker', url='https://www.docker.com/products/docker-desktop/'),
    dict(id='python', name='Python 3.11+', url='https://www.python.org/downloads/'),
    dict(id='node', name='Node.js', url='https://nodejs.org/'),
    dict(id='wsl', name='WSL 2', url='https://learn.microsoft.com/windows/wsl/install'),
]


def dependency_command(identifier):
    from . import tools
    if identifier == 'docker':
        cmd = docker_command()
        return [cmd] if cmd else None
    if identifier == 'python':
        if not hasattr(dependency_command, 'python'):
            dependency_command.python = tools.python_runtime()
        return dependency_command.python
    if identifier == 'node':
        return tools.node_command()
    if identifier == 'wsl' and sys_platform() == 'win32':
        if not hasattr(dependency_command, 'wsl'):
            try:
                result = capture(['wsl.exe', '--version'], timeout=8)
                # WSL localizes text; decode its UTF-16 output if necessary.
                text = result.stdout.decode('utf-16-le' if b'\x00' in result.stdout else 'utf-8', errors='replace')
                version = re.search(r'\d+\.\d+\.\d+', text)
                dependency_command.wsl = ['wsl.exe'] if result.returncode == 0 and version and tuple(map(int, version[0].split('.'))) >= (2, 1, 5) else None
            except (OSError, subprocess.TimeoutExpired):
                dependency_command.wsl = None
        return dependency_command.wsl
    return None


def clear_detection():
    for name in ('python', 'wsl'):
        if hasattr(dependency_command, name):
            delattr(dependency_command, name)
    from . import tools
    if hasattr(tools.catalog, 'python_available'):
        del tools.catalog.python_available


def missing_requirements(identifier):
    from . import tools
    # Reuse native ZAP without requiring Docker or WSL.
    if identifier == 'zap' and tools.native_zap_command():
        return []
    required = {'zap': ['docker'], 'sslyze': ['python'], 'wafw00f': ['python'], 'retire': ['node']}.get(identifier, [])
    if identifier == 'zap' and sys_platform() == 'win32':
        required = ['wsl', 'docker']
    if identifier == 'docker' and sys_platform() == 'win32':
        required = ['wsl']
    return [name for name in required if not dependency_command(name)]


def dependency_catalog():
    from . import tools
    with tools.LOCK:
        state = {key: dict(value) for key, value in tools.STATE.items()}
        positions = {key: index for index, key in enumerate(tools.INSTALL_QUEUE, 1)}
    rows = []
    for item in DEPENDENCIES:
        if item['id'] == 'wsl' and sys_platform() != 'win32':
            continue
        identifier = item['id']
        cmd = dependency_command(identifier)
        row = dict(item, status='ready' if cmd else 'missing', message='', location=' '.join(cmd or []), queue_position=positions.get(identifier))
        row.update(state.get(identifier, {}))
        if row['status'] not in ('installing', 'queued', 'action_required', 'error') and cmd:
            row['status'] = 'ready'
        rows.append(row)
    return rows


def install_python():
    system = sys_platform()
    if system == 'win32':
        winget = shutil.which('winget')
        if not winget:
            install_official_python(system)
        else:
            run([winget, 'install', '--id', 'Python.Python.3.13', '--exact', '--source', 'winget', '--interactive', '--accept-source-agreements'])
    elif system == 'darwin':
        from .tools import executable_candidates
        brew = next(executable_candidates('brew'), None)
        if not brew:
            install_official_python(system)
        else:
            run([brew, 'install', 'python@3.13'])
    elif system.startswith('linux'):
        cmd = linux_package_command('nmap')
        cmd[-1:] = ['python3', 'python3-venv'] if cmd[0] == 'apt-get' else ['python' if cmd[0] == 'pacman' else 'python3']
        privileged(cmd)
    else:
        raise ActionRequired('setup_unsupported')
    clear_detection()
    if not dependency_command('python'):
        raise ActionRequired('setup_runtime_missing')


def install_official_python(system):
    from .tools import download
    with tempfile.TemporaryDirectory(prefix='moth-python-') as temp:
        folder = Path(temp)
        index = folder / 'index.html'
        download('https://www.python.org/ftp/python/', index, 2_000_000)
        versions = set(re.findall(r'href="(3\.13\.\d+)/"', index.read_text()))
        if not versions:
            raise ValueError('No official stable Python 3.13 installer was found.')
        version = max(versions, key=lambda v: tuple(map(int, v.split('.'))))
        machine = platform.machine().lower()
        if machine not in ('amd64', 'x86_64', 'arm64', 'aarch64'):
            raise ActionRequired('setup_unsupported')
        arch = 'arm64' if machine in ('arm64', 'aarch64') else 'amd64'
        name = f'python-{version}-{arch}.exe' if system == 'win32' else f'python-{version}-macos11.pkg'
        path = folder / name
        download(f'https://www.python.org/ftp/python/{version}/{name}', path, 180_000_000)
        if system == 'win32':
            literal = "'" + str(path).replace("'", "''") + "'"
            script = "$s=Get-AuthenticodeSignature -LiteralPath " + literal + "; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notlike '*Python Software Foundation*') {exit 1}"
            run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], timeout=60)
            windows_installer(path)
        else:
            run(['/usr/sbin/pkgutil', '--check-signature', path], timeout=60)
            run(['/usr/sbin/spctl', '--assess', '--type', 'install', path], timeout=60)
            run(['/usr/bin/open', '-W', '-a', 'Installer', path])


def install_dependency(identifier):
    if identifier == 'node':
        from .tools import install_node
        install_node()
    elif identifier == 'python':
        install_python()
    elif identifier == 'wsl':
        windows_installer(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/wsl.exe', '--install --no-distribution')
        windows_installer(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/wsl.exe', '--update')
        clear_detection()
        if not dependency_command('wsl'):
            raise ActionRequired('setup_restart')
    elif identifier == 'docker':
        prepare_docker()
    else:
        raise ValueError('Unknown dependency.')
    clear_detection()
    if not dependency_command(identifier):
        raise ActionRequired('setup_runtime_missing')
