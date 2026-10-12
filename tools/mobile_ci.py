"""Host-side packaging and evidence verification; never dispatches a workflow."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

PREFIX = 'COMMONUTILS_MOBILE_RESULT='


def stage(source, destination):
    """Copy tracked Python sources only; never follow links or ship local settings."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source in destination.parents:
        raise ValueError('Stage outside the source checkout')
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', 'HEAD', '--', '*.py'],
                   check=True, stdout=subprocess.DEVNULL)
    tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z']).decode().split('\0')
    paths = [Path(name) for name in tracked if name.endswith('.py')]
    required = Path('tests/mobile_smoke.py')
    if required not in paths:
        raise ValueError('Commit the mobile smoke module before staging')
    package = destination / 'commonUtils'
    package.mkdir(parents=True, exist_ok=False)
    for relative in paths:
        original = source / relative
        if original.is_symlink() or any(parent.is_symlink() for parent in original.parents if parent != source):
            raise ValueError(f'Refusing linked source: {relative}')
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    (destination / 'source.json').write_text(json.dumps({'commonUtils_commit': revision}, indent=2) + '\n')


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
