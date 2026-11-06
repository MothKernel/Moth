"""Tool registry and isolated, on-demand installations from upstream sources."""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile
from collections import deque
from functools import lru_cache
from pathlib import Path
from .config import TOOLS
from .processes import external_environment, no_console_flags

PD = ("httpx", "nuclei", "katana", "dnsx", "subfinder")
REGISTRY = [
    dict(id="httpx", name="httpx", purpose="HTTP services, status and technologies", group="discovery", url="https://github.com/projectdiscovery/httpx"),
    dict(id="sslyze", name="SSLyze", purpose="TLS protocols and certificate configuration", group="assessment", url="https://github.com/nabla-c0d3/sslyze"),
    dict(id="katana", name="Katana", purpose="Same-host page and endpoint discovery", group="discovery", url="https://github.com/projectdiscovery/katana"),
    dict(id="zap", name="ZAP", purpose="One-page passive web analysis", group="assessment", url="https://www.zaproxy.org/download/"),
    dict(id="nuclei", name="Nuclei", purpose="Reviewed local configuration templates", group="assessment", url="https://github.com/projectdiscovery/nuclei"),
    dict(id="retire", name="Retire.js", purpose="Known vulnerable JavaScript libraries", group="assessment", url="https://github.com/RetireJS/retire.js"),
    dict(id="dnsx", name="dnsx", purpose="DNS records and hostname resolution", group="discovery", url="https://github.com/projectdiscovery/dnsx"),
    dict(id="wafw00f", name="WAFW00F", purpose="Web application firewall identification", group="discovery", url="https://github.com/EnableSecurity/wafw00f"),
    dict(id="subfinder", name="Subfinder", purpose="Passive subdomain discovery; results are not scanned", group="discovery", url="https://github.com/projectdiscovery/subfinder"),
    dict(id="nmap", name="Nmap", purpose="TCP connect checks on the target web port only", group="discovery", url="https://nmap.org/download.html"),
]
STATE = {}
LOCK = threading.Lock()
INSTALL_QUEUE = deque()
INSTALL_WORKER = None
EXE = ".exe" if os.name == "nt" else ""


def python_runtime():
    """A frozen application is not a Python CLI; never invoke itself with -m venv."""
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    candidates = []
    for name in (("py", "python", "python3") if os.name == "nt" else ("python3", "python")):
        path = shutil.which(name)
        if path and "windowsapps" not in path.lower() and Path(path).resolve() != Path(sys.executable).resolve():
            candidates.append([path, "-3"] if name == "py" else [path])
    for candidate in candidates:
        try:
            result = subprocess.run(candidate + ["-I", "-c", "import sys,venv; assert sys.version_info >= (3,11)"],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, env=external_environment(), creationflags=no_console_flags())
            if result.returncode == 0:
                return candidate
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def metadata(tool):
    return next((t for t in REGISTRY if t["id"] == tool), None)


def python_bin(folder):
    return folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def executable_candidates(*names):
    """PATH plus common user locations omitted by desktop-session PATHs."""
    folders = [Path.home() / ".local/bin", Path.home() / "go/bin", Path.home() / ".npm-global/bin",
               Path.home() / ".local/share/pnpm", Path("/usr/local/bin"), Path("/usr/bin")]
    for entry in os.environ.get("GOPATH", "").split(os.pathsep):
        if entry:
            folders.append(Path(entry) / "bin")
    seen = set()
    for name in names:
        found = shutil.which(name)
        candidates = ([Path(found)] if found else []) + [folder / (name + EXE) for folder in folders]
        for candidate in candidates:
            key = str(candidate)
            if key not in seen and candidate.is_file() and os.access(candidate, os.X_OK):
                seen.add(key)
                yield candidate


@lru_cache(maxsize=64)
def _is_pd_httpx(path, mtime, size):
    """Python HTTPX is a different application despite having the same CLI name."""
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.Popen([path, "-h"], stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                      env=external_environment(), creationflags=no_console_flags())
            try:
                result.wait(timeout=2)
            except subprocess.TimeoutExpired:
                result.kill()
                result.wait()
                return False
            output.seek(0)
            help_text = output.read(100_000).decode("utf-8", "replace").lower()
        return "-status-code" in help_text and "-tech-detect" in help_text
    except OSError:
        return False


def native_zap_command():
    # Arch's /usr/bin/zaproxy wrapper may discard arguments. Prefer the real script.
    if os.name != "nt":
        roots = [Path("/usr/share/zaproxy"), Path("/usr/share/zap"), Path("/opt/zaproxy"),
                 Path("/opt/ZAP"), Path("/Applications/ZAP.app/Contents/Java")]
        for root in roots:
            script = root / "zap.sh"
            if script.is_file() and os.access(script, os.X_OK):
                return [str(script)]
        for script in executable_candidates("zap.sh", "zaproxy", "owasp-zap"):
            # Prefer an argument-preserving script beside a wrapper where possible.
            direct = script.resolve().parent / "zap.sh"
            return [str(direct if direct.is_file() else script)]
    else:
        java = shutil.which("java")
        if java:
            for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
                base = Path(os.environ.get(variable, "C:/Program Files"))
                for root in (base / "ZAP/Zed Attack Proxy", base / "OWASP/Zed Attack Proxy", base / "ZAP"):
                    if root.is_dir():
                        jars = sorted(root.glob("zap-*.jar"), reverse=True)
                        if jars:
                            return [java, "-jar", str(jars[0])]
    return None


def is_docker_zap(cmd):
    return bool(cmd and len(cmd) == 2 and cmd[1].startswith("ghcr.io/zaproxy/zaproxy"))


def command(tool):
    folder = TOOLS / tool
    if tool in PD:
        aliases = ("httpx-toolkit", "httpx-pd", "httpx") if tool == "httpx" else (tool,)
        for candidate in executable_candidates(*aliases):
            if tool != "httpx":
                return [str(candidate)]
            try:
                stat = candidate.stat()
            except OSError:
                continue
            if _is_pd_httpx(str(candidate), stat.st_mtime_ns, stat.st_size):
                return [str(candidate)]
        path = folder / (tool + EXE)
        return [str(path)] if path.is_file() else None
    if tool in ("sslyze", "wafw00f"):
        system = next(executable_candidates(tool), None)
        if system:
            return [str(system)]
        path = python_bin(folder / "venv")
        entry = folder / "venv" / ("Scripts/wafw00f.exe" if os.name == "nt" else "bin/wafw00f")
        if (folder / "ready.json").exists() and path.exists():
            return [str(entry)] if tool == "wafw00f" and entry.exists() else [str(path), "-m", tool]
        return None
    if tool == "retire":
        if os.name != "nt":
            system = next(executable_candidates("retire", "retirejs"), None)
            if system:
                return [str(system)]
        node = node_command()
        if node:
            roots = [Path("/usr/lib/node_modules"), Path("/usr/local/lib/node_modules"),
                     Path.home() / ".npm-global/lib/node_modules", Path(os.environ.get("APPDATA", str(Path.home()))) / "npm/node_modules"]
            for root in roots:
                script = root / "retire/bin/retire"
                if script.is_file():
                    return node + [str(script)]
        script = folder / "node_modules/retire/bin/retire"
        return node + [str(script)] if node and script.exists() and (folder / "ready.json").exists() else None
    if tool == "zap":
        native = native_zap_command()
        if native:
            return native
        marker = folder / "ready.json"
        docker = shutil.which("docker")
        if docker and marker.exists():
            return [docker, json.loads(marker.read_text(encoding="utf-8"))["image"]]
        return None
    if tool == "nmap":
        system = next(executable_candidates("nmap"), None)
        candidates = [str(system) if system else None]
        if os.name == "nt":
            candidates += [str(Path(os.environ.get(root, "C:/Program Files")) / "Nmap/nmap.exe")
                           for root in ("ProgramFiles", "ProgramFiles(x86)")]
        return [next(p for p in candidates if p and Path(p).is_file())] if any(p and Path(p).is_file() for p in candidates) else None


def installation_source(tool, cmd):
    if tool == "zap" and is_docker_zap(cmd):
        return "docker"
    if cmd:
        folder = (TOOLS / tool).resolve()
        if any(Path(part).absolute().is_relative_to(folder) or Path(part).resolve().is_relative_to(folder)
               for part in cmd if not part.startswith("-")):
            return "moth"
        return "system"
    return ""


def catalog():
    with LOCK:
        state = {k: dict(v) for k, v in STATE.items()}
        positions = {tool: index for index, tool in enumerate(INSTALL_QUEUE, 1)}
    rows = []
    for tool in REGISTRY:
        identifier = tool["id"]
        cmd = command(identifier)
        ready = bool(cmd)
        source = installation_source(identifier, cmd)
        marker = TOOLS / identifier / "ready.json"
        version = ""
        if marker.exists() and source in ("moth", "docker"):
            try:
                details = json.loads(marker.read_text(encoding="utf-8"))
                version = details.get("version", details.get("image", ""))
            except (OSError, ValueError):
                pass
        row = dict(tool, status="ready" if ready else "missing", version=version, message="", automatic=identifier != "nmap",
                   source=source, location=" ".join(cmd) if cmd else "")
        row.update(state.get(identifier, {}))
        row["queue_position"] = positions.get(identifier)
        if ready and row["status"] not in ("installing", "queued"):
            row.update(status="ready", message=row["message"] if row.get("update_failed") else "")
        if identifier == "zap" and not ready and not shutil.which("docker"):
            row.update(status="prerequisite", message="Install and start Docker Desktop/Engine first.")
        if identifier == "nmap" and not ready:
            row.update(status="manual", message="Use the official installer; redistribution requires a license review.")
        if identifier in ("sslyze", "wafw00f") and not ready and getattr(sys, "frozen", False):
            # Cache the bounded runtime probe; do not spawn processes on every UI refresh.
            if not hasattr(catalog, "python_available"):
                catalog.python_available = bool(python_runtime())
            if not catalog.python_available:
                row.update(status="prerequisite", message="Install Python 3.11+ to enable this optional Python-based scanner.", url="https://www.python.org/downloads/")
        rows.append(row)
    from . import updates
    checked = updates.snapshot()
    for row in rows:
        result = checked.get(row["id"], {})
        if result.get("update_location") == row["location"] and result.get("update_version") == row["version"]:
            row.update(result)
    return rows


def download(url, destination, limit=180_000_000):
    if not url.startswith("https://"):
        raise ValueError("Downloads must use HTTPS.")
    request = urllib.request.Request(url, headers={"User-Agent": "Moth/0.1", "Accept": "application/octet-stream"})
    total = 0
    with urllib.request.urlopen(request, timeout=45) as source, open(destination, "wb") as out:
        while chunk := source.read(128 * 1024):
            total += len(chunk)
            if total > limit:
                raise ValueError("Download exceeded the size limit.")
            out.write(chunk)


def remote_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Moth/0.1", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(3_000_001)
    if len(data) > 3_000_000:
        raise ValueError("Release metadata is too large.")
    return json.loads(data)


def verify_checksum(archive, checksum_file):
    expected = None
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[-1].lstrip("*") == archive.name:
            expected = fields[0].lower()
    with archive.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if expected is None or len(expected) != 64 or actual != expected:
        raise ValueError("SHA-256 checksum verification failed; installation refused.")


def native_platform():
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macOS"}.get(platform.system())
    arch = {"x86_64": "amd64", "AMD64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine())
    if not system or not arch:
        raise ValueError("This operating system or architecture is not supported yet.")
    return system, arch


def install_pd(tool, folder):
    system, arch = native_platform()
    release = remote_json(f"https://api.github.com/repos/projectdiscovery/{tool}/releases/latest")
    assets = release["assets"]
    suffix = f"_{system}_{arch}.zip"
    asset = next((a for a in assets if a["name"].endswith(suffix)), None)
    checksums = next((a for a in assets if a["name"].endswith("checksums.txt")), None)
    if not asset or not checksums:
        raise ValueError("No compatible upstream archive with checksums was found.")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset["name"]
        check = Path(tmp) / "checksums.txt"
        download(asset["browser_download_url"], archive)
        download(checksums["browser_download_url"], check, 2_000_000)
        verify_checksum(archive, check)
        with zipfile.ZipFile(archive) as zipped:
            member = next(m for m in zipped.infolist() if m.filename == tool + EXE)
            if member.file_size > 250_000_000:
                raise ValueError("Executable is unexpectedly large.")
            temporary = folder / (tool + EXE + ".download")
            with zipped.open(member) as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target)
            temporary.chmod(0o755)
            temporary.replace(folder / (tool + EXE))
    (folder / "ready.json").write_text(json.dumps({"version": release["tag_name"], "source": asset["browser_download_url"]}))


def run_install(args, timeout=600):
    """Installer output stays local, bounded on read; no shell interpolation."""
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL, env=external_environment(), creationflags=no_console_flags())
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise ValueError("Installation timed out.")
        if code:
            log.seek(0, 2)
            log.seek(max(0, log.tell() - 2500))
            raise ValueError(log.read().decode("utf-8", "replace"))


def node_command():
    managed = TOOLS / "node" / ("node.exe" if os.name == "nt" else "bin/node")
    system = shutil.which("node")
    return [str(managed)] if managed.exists() and (TOOLS / "node/ready.json").exists() else ([system] if system else None)


def install_node():
    if node_command():
        return
    system, arch = native_platform()
    version = next(v["version"] for v in remote_json("https://nodejs.org/dist/index.json") if v["lts"])
    node_system = {"windows": "win", "linux": "linux", "macOS": "darwin"}[system]
    node_arch = "x64" if arch == "amd64" else "arm64"
    prefix = f"node-{version}-{node_system}-{node_arch}"
    name = prefix + (".zip" if os.name == "nt" else ".tar.xz")
    folder = TOOLS / "node"
    folder.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / name
        checksums = Path(tmp) / "SHASUMS256.txt"
        download(f"https://nodejs.org/dist/{version}/{name}", archive)
        download(f"https://nodejs.org/dist/{version}/SHASUMS256.txt", checksums, 1_000_000)
        verify_checksum(archive, checksums)
        # Extract regular files only, under a validated root. npm is invoked via its JS entry point.
        total_size = 0
        file_count = 0
        def target(name, size):
            nonlocal total_size, file_count
            total_size += size
            file_count += 1
            if total_size > 600_000_000 or file_count > 30_000:
                raise ValueError("Runtime archive exceeded the extraction limit.")
            relative = Path(name).relative_to(prefix)
            destination = (folder / relative).resolve()
            if not destination.is_relative_to(folder.resolve()) or size > 180_000_000:
                raise ValueError("Unsafe runtime archive entry.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            return destination
        if os.name == "nt":
            with zipfile.ZipFile(archive) as z:
                for item in z.infolist():
                    if not item.is_dir():
                        target(item.filename, item.file_size).write_bytes(z.read(item))
        else:
            with tarfile.open(archive) as tar:
                for item in tar:
                    if item.isfile():
                        out = target(item.name, item.size)
                        with tar.extractfile(item) as source, out.open("wb") as dest:
                            shutil.copyfileobj(source, dest)
                        out.chmod(item.mode & 0o755)
    (folder / "ready.json").write_text(json.dumps({"version": version}))


def install(tool):
    folder = TOOLS / tool
    folder.mkdir(exist_ok=True)
    try:
        if tool in PD:
            install_pd(tool, folder)
        elif tool in ("sslyze", "wafw00f"):
            env = folder / "venv"
            if not python_bin(env).exists():
                runtime = python_runtime()
                if runtime is None:
                    raise ValueError("Install Python 3.11+ to enable this optional scanner.")
                run_install(runtime + ["-m", "venv", str(env)])
            run_install([str(python_bin(env)), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", tool])
            version = subprocess.check_output([str(python_bin(env)), "-c", "import importlib.metadata, sys; print(importlib.metadata.version(sys.argv[1]))", tool], timeout=20, text=True, env=external_environment()).strip()
            (folder / "ready.json").write_text(json.dumps({"source": "PyPI", "package": tool, "version": version}))
        elif tool == "retire":
            install_node()
            node = node_command()
            root = Path(node[0]).parent
            possible = [root / "node_modules/npm/bin/npm-cli.js", root.parent / "lib/node_modules/npm/bin/npm-cli.js",
                        Path("/usr/share/nodejs/npm/bin/npm-cli.js"), Path("/usr/lib/node_modules/npm/bin/npm-cli.js")]
            npm_script = next((p for p in possible if p.exists()), None)
            if not npm_script:
                raise ValueError("npm was not found beside Node.js. Install Node.js with npm and retry.")
            run_install(node + [str(npm_script), "install", "--prefix", str(folder), "--ignore-scripts", "--no-audit", "--no-fund", "retire"])
            version = json.loads((folder / "node_modules/retire/package.json").read_text(encoding="utf-8"))["version"]
            (folder / "ready.json").write_text(json.dumps({"source": "npm", "package": "retire", "version": version}))
        elif tool == "zap":
            docker = shutil.which("docker")
            if not docker:
                raise ValueError("Docker Desktop/Engine must be installed and running first.")
            image = "ghcr.io/zaproxy/zaproxy:stable"
            run_install([docker, "pull", image], timeout=1200)
            digest = subprocess.check_output([docker, "image", "inspect", image, "--format", "{{index .RepoDigests 0}}"], timeout=20, text=True, env=external_environment()).strip()
            if not digest.startswith("ghcr.io/zaproxy/zaproxy@sha256:"):
                raise ValueError("Could not pin the ZAP container image digest.")
            (folder / "ready.json").write_text(json.dumps({"image": digest}))
        else:
            raise ValueError("Use the official Nmap installer.")
        with LOCK:
            STATE[tool] = dict(status="ready", message="Installation completed.")
    except Exception as exc:
        with LOCK:
            STATE[tool] = dict(status="error", message=str(exc)[-2500:])


def _process_install_queue():
    global INSTALL_WORKER
    while True:
        with LOCK:
            if not INSTALL_QUEUE:
                INSTALL_WORKER = None
                return
            tool = INSTALL_QUEUE.popleft()
            updating = STATE[tool].get("operation") == "update"
            STATE[tool] = dict(status="installing", operation="update" if updating else "install", message="Downloading and preparing dependencies…")
        try:
            # Detection may change while a tool waits in the queue.
            if command(tool) and not updating:
                with LOCK:
                    STATE[tool] = dict(status="ready", message="")
            else:
                install(tool)
            with LOCK:
                failed = STATE[tool]["status"] == "error"
                if failed and updating:
                    STATE[tool]["update_failed"] = True
            if not failed:
                from . import updates
                updates.invalidate(tool)
        except Exception as exc:
            # An unexpected failure must not prevent later installations.
            with LOCK:
                STATE[tool] = dict(status="error", update_failed=updating, message=str(exc)[-2500:])


def start_install(tool, update=False):
    global INSTALL_WORKER
    if not metadata(tool):
        raise ValueError("Unknown tool.")
    if tool == "nmap":
        raise ValueError("Install Nmap from its official website, then refresh detection.")
    cmd = command(tool)
    if cmd and not update:
        return
    if update and (not cmd or installation_source(tool, cmd) not in ("moth", "docker")):
        raise ValueError("Update this installation through its package manager or official installer.")
    with LOCK:
        if STATE.get(tool, {}).get("status") in ("installing", "queued"):
            return
        INSTALL_QUEUE.append(tool)
        STATE[tool] = dict(status="queued", operation="update" if update else "install", message="")
        if INSTALL_WORKER is None:
            INSTALL_WORKER = threading.Thread(target=_process_install_queue, daemon=True)
            try:
                INSTALL_WORKER.start()
            except Exception:
                INSTALL_WORKER = None
                INSTALL_QUEUE.remove(tool)
                STATE.pop(tool, None)
                raise
