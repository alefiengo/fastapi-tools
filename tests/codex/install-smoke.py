#!/usr/bin/env python3
"""Optional actual local installation in a disposable CODEX_HOME. No model calls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    with tempfile.TemporaryDirectory(prefix='fastapi-install-smoke-') as temporary:
        base = Path(temporary)
        config = base / 'codex-home'
        config.mkdir()
        market = base / 'market'
        catalog = market / '.agents/plugins/marketplace.json'
        catalog.parent.mkdir(parents=True)
        (market / 'fastapi-tools').symlink_to(ROOT, target_is_directory=True)
        catalog.write_text(json.dumps({
            'name': 'fastapi-local', 'interface': {'displayName': 'FastAPI local'},
            'plugins': [{'name': 'fastapi-tools',
                         'source': {'source': 'local', 'path': './fastapi-tools'},
                         'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_USE'}}],
        }))
        environment = {**os.environ, 'CODEX_HOME': str(config)}

        def command(arguments):
            result = subprocess.run(['codex', *arguments], cwd=base, env=environment,
                                    capture_output=True, text=True, timeout=40)
            assert result.returncode == 0, result.stdout + result.stderr
            return json.loads(result.stdout)

        added = command(['plugin', 'marketplace', 'add', str(market), '--json'])
        assert added['marketplaceName'] == 'fastapi-local', added
        installed = command(['plugin', 'add', 'fastapi-tools@fastapi-local', '--json'])
        version = json.loads((ROOT / '.codex-plugin/plugin.json').read_text())['version']
        assert installed['version'] == version, installed
        destination = Path(installed['installedPath']).resolve()
        assert destination.is_relative_to(config), installed
        assert (destination / '.codex-plugin/plugin.json').is_file(), installed
        plugins = command(['plugin', 'list', '--json'])['installed']
        assert len(plugins) == 1, plugins
        assert plugins[0]['enabled'] is True and plugins[0]['installed'] is True, plugins
        assert plugins[0]['version'] == version, plugins
        print(f'PASS local marketplace add/install/list: {version}, enabled; disposable CODEX_HOME, no model calls')


if __name__ == '__main__':
    main()
