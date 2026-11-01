"""Local FastAPI scaffold. No network, installers, application imports or commands.

Publication requires the OS exclusive rename primitive; never fall back to a
check followed by plain rename, which can replace a racing empty directory.
"""
import ctypes
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sys


MARKERS = {'pyproject.toml', 'setup.py', 'setup.cfg', 'requirements.txt',
           'uv.lock', 'poetry.lock', 'Pipfile', 'Pipfile.lock', '__init__.py',
           '.venv', 'venv', '.git', '.hg', 'package.json', 'pnpm-workspace.yaml',
           'lerna.json', 'Cargo.toml', 'go.work', 'go.mod', 'pom.xml',
           'settings.gradle', 'settings.gradle.kts', 'build.gradle', 'build.gradle.kts'}


@contextmanager
def publication_step():
    """Defer cancellation until resource ownership bookkeeping is consistent."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def protected(directory):
    # Inspect names only, including dangling symlinks; do not follow metadata.
    with os.scandir(directory) as entries:
        for index, entry in enumerate(entries):
            if index >= 100000:
                raise ValueError('Ancestor inventory exceeds safety limit')
            if (entry.name in MARKERS or entry.name.endswith('.code-workspace')
                    or entry.name.startswith('requirements') and entry.name.endswith('.txt')):
                raise ValueError(f'Existing Python project or workspace ancestor: {entry.name}')


def open_parent(target):
    """Walk every ancestor without following symlinks and inspect each one."""
    handle = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        protected(handle)
        for part in target.parent.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=handle)
            os.close(handle)
            handle = child
            protected(handle)
        return handle
    except BaseException:
        os.close(handle)
        raise


def absent(parent, name):
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ValueError('destination must be absent, including files, directories and dangling symlinks')


def publish(parent, stage, destination):
    # Linux man-pages rename(2); Apple xnu bsd/sys/stdio.h (RENAME_EXCL).
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        rename, flags = libc.renameat2, 1  # RENAME_NOREPLACE
    elif sys.platform == 'darwin' and hasattr(libc, 'renameatx_np'):
        rename, flags = libc.renameatx_np, 4  # RENAME_EXCL
    else:
        raise ValueError('Exclusive directory publication unavailable on this platform')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent, os.fsencode(stage), parent, os.fsencode(destination), flags):
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise ValueError('destination appeared during initialization; nothing replaced')
        raise OSError(code, os.strerror(code))


def scaffold(name):
    return {
        'pyproject.toml': f'''[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = {json.dumps(name)}
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi[standard]"]

[project.optional-dependencies]
test = ["pytest", "httpx"]

[tool.setuptools.packages.find]
include = ["app*"]

[tool.fastapi]
entrypoint = "app.main:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
''',
        'app/__init__.py': '',
        'app/main.py': '''from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}
''',
        'tests/test_main.py': '''from fastapi.testclient import TestClient

from app.main import app


def test_root():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}
''',
        '.gitignore': '.venv/\n__pycache__/\n*.egg-info/\n.pytest_cache/\n.fastapi-tools/\n.env\nbuild/\ndist/\n',
        'README.md': f'''# {name}

Generated locally by fastapi-tools. No dependencies installed or code executed.
Python 3.11 or later is required. After reviewing the files, set up manually:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest
fastapi dev
```

The application serves `/`; interactive API docs are at `/docs`.
Dependencies are unpinned declarations. Resolve and lock versions before deployment.
''',
    }


def write_scaffold(stage, files):
    for name, content in files.items():
        parts = name.split('/')
        parent = os.dup(stage)
        try:
            for part in parts[:-1]:
                try:
                    os.mkdir(part, 0o700, dir_fd=parent)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = child
            fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                output.write(content)
        finally:
            os.close(parent)


def initialize_project(request):
    if request.get('explicitRequest') is not True:
        raise ValueError('Initialization requires an explicit user request (explicitRequest=true)')
    raw, name = request.get('destination'), request.get('projectName')
    if (not isinstance(raw, str) or not raw.startswith('/') or raw.startswith('//')
            or len(raw) > 4096 or '\\' in raw or any(ord(c) < 32 for c in raw)
            or any(part in ('', '.', '..') for part in raw.split('/')[1:])):
        raise ValueError('destination must be an absolute directory path without traversal or symlinks')
    if (not isinstance(name, str) or len(name) > 100
            or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?', name)):
        raise ValueError('projectName must be a valid Python distribution name (1-100 characters)')
    target = Path(raw)
    files = scaffold(name)
    parent = open_parent(target)
    stage = None
    try:
        absent(parent, target.name)
        candidate = '.fastapi-tools-init-' + secrets.token_hex(16)
        with publication_step():
            os.mkdir(candidate, 0o700, dir_fd=parent)
            stage = candidate
        fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            write_scaffold(fd, files)
        finally:
            os.close(fd)
        current = open_parent(target)
        try:
            original, latest = os.fstat(parent), os.fstat(current)
            if (original.st_dev, original.st_ino) != (latest.st_dev, latest.st_ino):
                raise ValueError('destination parent changed during initialization')
        finally:
            os.close(current)
        absent(parent, target.name)
        with publication_step():
            publish(parent, stage, target.name)
            stage = None
        return {'ok': True, 'exitCode': 0, 'destination': str(target), 'projectName': name,
                'files': sorted(files), 'source': 'local-template',
                'dependenciesInstalled': False, 'codeExecuted': False}
    finally:
        try:
            if stage is not None:
                shutil.rmtree(stage, dir_fd=parent)
        finally:
            os.close(parent)
