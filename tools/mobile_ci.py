"""Host-side packaging and evidence verification; never dispatches a workflow."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

PREFIX = 'COMMONUTILS_MOBILE_RESULT='


def stage(source, destination, *, allow_dirty=False):
    """Copy Python and optional native UI bridges; reject linked/local settings."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source in destination.parents:
        raise ValueError('Stage outside the source checkout')
    dirty = bool(subprocess.check_output(['git', '-C', str(source), 'diff', '--name-only', 'HEAD', '--', '*.py', 'ui/native/**/*.java']))
    if dirty and not allow_dirty:
        raise ValueError('Commit shared Python sources before staging, or explicitly allow a local development payload.')
    tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z']).decode().split('\0')
    paths = sorted({Path(name) for name in tracked if name.endswith('.py')})
    native_root = source / 'ui/native'
    native_paths = {path.relative_to(source) for path in native_root.rglob('*')
                    if path.is_file() and path.suffix in {'.py', '.java'}}
    untracked_native = native_paths - {Path(name) for name in tracked}
    if untracked_native and not allow_dirty:
        raise ValueError('Commit native UI sources before release staging.')
    dirty = dirty or bool(untracked_native)
    paths = sorted(set(paths) | native_paths)
    required = Path('tests/mobile_smoke.py')
    if required not in paths:
        raise ValueError('Commit the mobile smoke module before staging')
    package = destination / 'commonUtils'
    package.mkdir(parents=True, exist_ok=False)
    for relative in paths:
        original = source / relative
        if allow_dirty and not original.exists() and not original.is_symlink():
            continue  # A tracked deletion is part of this explicit development snapshot.
        if original.is_symlink() or any(parent.is_symlink() for parent in original.parents if parent != source):
            raise ValueError(f'Refusing linked source: {relative}')
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    (destination / 'source.json').write_text(json.dumps({'commonUtils_commit': revision, 'commonUtils_dirty': dirty}, indent=2) + '\n')


def verify(log, target, output):
    """Require one complete passing report from the actual target runtime."""
    reports = []
    for line in Path(log).read_text(encoding='utf-8', errors='replace').splitlines():
        if line.startswith(PREFIX):
            reports.append(json.loads(line[len(PREFIX):]))
    if len(reports) != 1:
        raise ValueError('Expected exactly one complete mobile result; inspect the testbed log')
    report = reports[0]
    expected_environment = {'ios': 'ios-simulator', 'android': 'android-emulator'}[target]
    if (report.get('schema') != 1 or report.get('suite') != 'commonUtils-mobile-smoke'
            or report.get('target') != target or report.get('sys_platform') != target
            or report.get('environment') != expected_environment or report.get('success') is not True
            or any(report.get(name) != 0 for name in ('failures', 'errors', 'skipped'))
            or report.get('tests_run') != 7 or len(set(report.get('expected_tests', []))) != 7):
        raise ValueError('Mobile smoke evidence is incomplete, failed, skipped, or from the wrong runtime')
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('stage')
    prepare.add_argument('source', type=Path)
    prepare.add_argument('destination', type=Path)
    check = commands.add_parser('verify')
    check.add_argument('log', type=Path)
    check.add_argument('--target', choices=('ios', 'android'), required=True)
    check.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'stage':
        stage(args.source, args.destination)
    else:
        verify(args.log, args.target, args.output)


if __name__ == '__main__':
    main()
