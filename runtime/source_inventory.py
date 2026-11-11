#!/usr/bin/env python3
"""Bounded project source inventory and syntax check (standard library only).

The syntax check runs under the application's interpreter, which can be older
than the plugin runtime. Keep this module compatible with Python 3.8: no
tomllib, no match statements and no 3.9+ path or string helpers.
"""
import os
from pathlib import Path
import stat
import sys

IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', '__pycache__', '.idea', '.vscode',
           '.pytest_cache', '.ruff_cache', '.mypy_cache', '.fastapi-tools', 'htmlcov', '.tox', '.nox',
           '.hypothesis', '.eggs', '.claude'}
SOURCE_LIMIT_FILES = 50000
SOURCE_LIMIT_BYTES = 128 * 1024 * 1024


def read_regular(path, limit=8 * 1024 * 1024):
    """Bound static reads, reject symlinks/FIFOs/devices without blocking."""
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValueError('Unsafe or oversized input: {}'.format(path))
        content = source.read(limit + 1)
        if len(content) > limit:
            raise ValueError('Input exceeds safety limit: {}'.format(path))
        return content


def ignored_directory(path, root):
    """Generated, tool and environment directories are never project inputs."""
    if path.name in ('build', 'dist') and ('src' in path.relative_to(root).parts or (path / '__init__.py').is_file()):
        return False
    if path.name in IGNORED or path.name.endswith('.egg-info'):
        return True
    # Any virtual environment, whatever its name (env/, .env/, venv311/...).
    return (path / 'pyvenv.cfg').is_file() and not (path / 'pyvenv.cfg').is_symlink()


def _skipped_target(target, root):
    """Resolved directory inside root that the walk never visits in place."""
    try:
        parts = target.relative_to(root).parts
    except ValueError:
        return False  # External sources are not inspected (the fingerprint refuses them).
    for index in range(len(parts)):
        prefix = root.joinpath(*parts[:index + 1])
        if prefix.is_dir() and ignored_directory(prefix, root):
            return True
    return False


def source_files(root):
    root = Path(root)
    resolved_root = root.resolve()
    count = [0, 0]

    def walk_error(error):
        raise error

    def checked(file):
        metadata = file.stat()
        count[0] += 1
        count[1] += metadata.st_size
        if not stat.S_ISREG(metadata.st_mode) or count[0] > SOURCE_LIMIT_FILES or count[1] > SOURCE_LIMIT_BYTES:
            raise ValueError('Python source inventory exceeds safety limit or contains nonregular files')
        return file

    linked = []
    for folder, directories, filenames in os.walk(str(root), followlinks=False, onerror=walk_error):
        kept = []
        for d in sorted(directories):
            path = Path(folder) / d
            if path.is_symlink():
                target = path.resolve()
                if target.is_dir() and _skipped_target(target, resolved_root) and target not in linked:
                    linked.append(target)  # e.g. gen -> build/gen: still application source
            elif not ignored_directory(path, root):
                kept.append(d)
        directories[:] = kept
        for name in sorted(filenames):
            file = Path(folder) / name
            if file.suffix == '.py' and not file.is_symlink():
                yield checked(file)
    for target in linked:
        target = root / target.relative_to(resolved_root)
        for folder, directories, filenames in os.walk(str(target), followlinks=False, onerror=walk_error):
            directories[:] = sorted(d for d in directories if not (Path(folder) / d).is_symlink())
            for name in sorted(filenames):
                file = Path(folder) / name
                if file.suffix == '.py' and not file.is_symlink():
                    yield checked(file)


def syntax_check(root):
    for file in source_files(root):
        compile(read_regular(file), str(file), 'exec')
    print('Python syntax check passed')


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--syntax':
        sys.exit('usage: source_inventory.py --syntax PROJECT_ROOT')
    syntax_check(Path(sys.argv[2]))
