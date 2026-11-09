import hashlib
import subprocess
from pathlib import Path
import pytest
from moth import system_install as setup, tools


@pytest.fixture(autouse=True)
def clean_detection(monkeypatch):
    setup.clear_detection()
    monkeypatch.setattr(tools, 'STATE', {})
    yield
    setup.clear_detection()


@pytest.mark.parametrize('release,tool,expected', [
    ({'ID':'arch'},'zap',['pacman','-S','--needed','--noconfirm','docker']),
    ({'ID':'ubuntu','ID_LIKE':'debian'},'nmap',['apt-get','install','-y','nmap']),
    ({'ID':'debian'},'zap',['apt-get','install','-y','docker.io']),
    ({'ID':'fedora'},'zap',['dnf','install','-y','moby-engine']),
    ({'ID':'opensuse-tumbleweed'},'zap',['zypper','--non-interactive','install','docker']),
])
def test_supported_linux_installers(release,tool,expected):
    assert setup.linux_package_command(tool,release)==expected


def test_unknown_distribution_never_executes_guessed_installation():
    with pytest.raises(setup.ActionRequired,match='setup_unsupported'):
        setup.linux_package_command('zap',{'ID':'unknown'})


def test_zap_never_downloads_missing_docker(monkeypatch):
    monkeypatch.setattr(setup,'docker_command',lambda:None)
    monkeypatch.setattr(setup,'docker_download',lambda *args:pytest.fail('Unrequested dependency installation'))
    with pytest.raises(setup.ActionRequired,match='setup_docker_missing'):
        setup.ensure_docker()


def test_windows_zap_recommends_both_missing_dependencies(monkeypatch):
    monkeypatch.setattr(setup,'sys_platform',lambda:'win32')
    monkeypatch.setattr(tools,'native_zap_command',lambda:None)
    monkeypatch.setattr(setup,'dependency_command',lambda tool:None)
    assert setup.missing_requirements('zap')==['wsl','docker']
    with pytest.raises(ValueError,match='WSL 2, Docker'):
        tools.start_install('zap')
    assert not tools.STATE


def test_native_zap_needs_no_docker_or_wsl(monkeypatch):
    monkeypatch.setattr(tools,'native_zap_command',lambda:['native-zap'])
    monkeypatch.setattr(setup,'dependency_command',lambda tool:pytest.fail('Unneeded probe'))
    assert setup.missing_requirements('zap')==[]


def test_docker_dependency_is_not_ready_until_engine_works(monkeypatch,tmp_path):
    monkeypatch.setattr(tools,'TOOLS',tmp_path)
    monkeypatch.setattr(setup,'prepare_docker',lambda:(_ for _ in ()).throw(setup.ActionRequired('setup_restart')))
    tools.install('docker')
    assert tools.STATE['docker']['status']=='action_required'
    assert tools.STATE['docker']['message_key']=='setup_restart'


def test_existing_linux_engine_reused_without_installer_or_privilege(monkeypatch):
    monkeypatch.setattr(setup,'sys_platform',lambda:'linux')
    monkeypatch.setattr(setup,'docker_command',lambda:'/bin/docker')
    monkeypatch.setattr(setup,'capture',lambda *args,**kw:subprocess.CompletedProcess(args,0,b'linux\n',b''))
    monkeypatch.setattr(setup,'privileged',lambda *args:pytest.fail('Unneeded elevation'))
    assert setup.ensure_docker()=='/bin/docker'


def test_windows_installer_path_is_literal_and_waits(monkeypatch):
    calls=[]
    monkeypatch.setattr(setup,'run',lambda args,**kw:calls.append(args))
    setup.windows_installer(Path("C:/Users/O'Brien/Moth installer.exe"),'install')
    script=calls[0][-1]
    assert "O''Brien" in script
    assert '-Verb RunAs -Wait -PassThru' in script
    assert '-ArgumentList \'install\'' in script


def test_docker_checksum_accepts_space_in_official_filename(tmp_path):
    archive=tmp_path/'Docker Desktop Installer.exe'
    archive.write_bytes(b'installer')
    checksums=tmp_path/'checksums.txt'
    checksums.write_text(hashlib.sha256(b'installer').hexdigest()+' *'+archive.name+'\n')
    tools.verify_checksum(archive,checksums)
    archive.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='checksum'):
        tools.verify_checksum(archive,checksums)


def test_nmap_upstream_digest_checked_before_launch(monkeypatch,tmp_path):
    payload=b'official installer'
    digest=hashlib.sha256(payload).hexdigest().upper()
    def download(url,path,limit):
        if url.endswith('digest.txt'):
            path.write_text('SHA256 = '+' '.join(digest[i:i+8] for i in range(0,64,8))+'\nSHA512 = AB CD\n')
        else:path.write_bytes(payload)
    monkeypatch.setattr(tools,'download',download)
    path=setup.verified_download('https://nmap.org/installer','nmap-7.993-setup.exe','https://nmap.org/digest.txt',tmp_path,nmap=True)
    assert path.read_bytes()==payload


def test_tampered_nmap_installer_is_rejected(monkeypatch,tmp_path):
    def download(url,path,limit):
        path.write_text('SHA256 = '+'0'*64+'\n' if url.endswith('digest.txt') else 'tampered')
    monkeypatch.setattr(tools,'download',download)
    with pytest.raises(ValueError,match='checksum'):
        setup.verified_download('https://nmap.org/installer','nmap.exe','https://nmap.org/digest.txt',tmp_path,nmap=True)


def test_docker_windows_containers_not_treated_as_ready(monkeypatch):
    monkeypatch.setattr(setup,'sys_platform',lambda:'win32')
    monkeypatch.setattr(setup,'docker_command',lambda:'docker.exe')
    monkeypatch.setattr(setup,'capture',lambda *a,**k:subprocess.CompletedProcess(a,0,b'windows\n',b''))
    monkeypatch.setattr(setup,'start_desktop',lambda *a:None)
    with pytest.raises(setup.ActionRequired,match='setup_linux_containers'):
        setup.ensure_docker()


def test_nmap_not_reported_installed_if_wizard_was_cancelled(monkeypatch,tmp_path):
    monkeypatch.setattr(setup,'sys_platform',lambda:'win32')
    monkeypatch.setattr(setup,'official_nmap',lambda *a:tmp_path/'installer.exe')
    monkeypatch.setattr(setup,'windows_installer',lambda *a:None)
    monkeypatch.setattr(tools,'command',lambda *a:None)
    with pytest.raises(setup.ActionRequired,match='setup_nmap_missing'):
        setup.install_nmap()


def test_windows_restart_exit_code_is_action_required(monkeypatch,tmp_path):
    monkeypatch.setattr(setup,'run',lambda *args,**kwargs:3010)
    with pytest.raises(setup.ActionRequired,match='setup_restart'):
        setup.windows_installer(tmp_path/'setup.exe')


def test_unsigned_python_fallback_is_not_executed(monkeypatch):
    def download(url,path,limit):
        path.write_text('href="3.13.9/"' if url.endswith('/ftp/python/') else 'fake installer')
    monkeypatch.setattr(tools,'download',download)
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        raise ValueError('Signature rejected')
    monkeypatch.setattr(setup,'run',run)
    monkeypatch.setattr(setup,'windows_installer',lambda *args:pytest.fail('Unsigned installer executed'))
    with pytest.raises(ValueError,match='Signature rejected'):
        setup.install_official_python('win32')
    assert 'Get-AuthenticodeSignature' in calls[0][-1]
    assert 'Python Software Foundation' in calls[0][-1]


def test_wsl_localized_utf16_version_detection(monkeypatch):
    monkeypatch.setattr(setup,'sys_platform',lambda:'win32')
    monkeypatch.setattr(setup,'capture',lambda *args,**kwargs:subprocess.CompletedProcess(args,0,'Версия WSL: 2.6.1\r\n'.encode('utf-16-le'),b''))
    assert setup.dependency_command('wsl')==['wsl.exe']


def test_old_wsl_is_recommended_for_update(monkeypatch):
    monkeypatch.setattr(setup,'sys_platform',lambda:'win32')
    monkeypatch.setattr(setup,'capture',lambda *args,**kwargs:subprocess.CompletedProcess(args,0,b'WSL version: 1.2.0\r\n',b''))
    assert setup.dependency_command('wsl') is None
