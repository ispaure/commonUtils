"""Run actual Unix launchers with a controlled uv transport."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class ArgumentTests(unittest.TestCase):
    def test_actual_unix_launchers_forward_boundaries_and_exit_code(self):
        if os.name == 'nt':
            self.skipTest('Bash launcher contract')
        base = Path(__file__).resolve().parents[2] / 'launchers'
        with tempfile.TemporaryDirectory(prefix='launcher café space ') as value:
            root = Path(value)
            for name, text in {'.python-version':'3.12.2', 'pyproject.toml':'[project]\nname="fixture"\nversion="0"',
                               'uv.lock':'fixture', 'launch.py':'pass'}.items():
                (root/name).write_text(text)
            (root/'config.ini').write_text('[Launch]\nsource_dir=.\nlaunch_file=launch\n')
            (root/'.venv').mkdir()
            binaries = root/'bin'; binaries.mkdir()
            (binaries/'uv').write_text('#!/bin/bash\nif [[ "$1" == run ]]; then shift 6; python3 -c \'import json,sys;print(json.dumps(sys.argv[1:]))\' "$@"; exit 7; fi\nexit 0\n')
            (binaries/'uv').chmod(0o755)
            (binaries/'uname').write_text('#!/bin/bash\nif [[ "$1" == -s ]]; then echo "$FAKE_OS"; else echo arm64; fi\n')
            (binaries/'uname').chmod(0o755)
            # launchers prepend ~/.local/bin; isolate HOME so only our fixture uv runs.
            for name, system in [('LaunchPythonProject_MAC.command','Darwin'),('LaunchPythonProject_LINUX_UV.sh','Linux')]:
                result = subprocess.run(['bash',str(base/name),str(root),str(root/'config.ini'),'false',
                                         'space value','quote"value','literal&value','café'],
                    capture_output=True,text=True,cwd='/',timeout=20,
                    env=dict(os.environ,HOME=str(root),PATH=str(binaries)+os.pathsep+os.environ['PATH'],FAKE_OS=system))
                self.assertEqual(result.returncode,7,result.stdout+result.stderr)
                row = next(json.loads(line) for line in result.stdout.splitlines() if line.startswith('['))
                self.assertEqual(row,['space value','quote"value','literal&value','café'])
