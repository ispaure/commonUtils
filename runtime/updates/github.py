"""Public GitHub commit checks and bounded, commit-pinned source snapshots."""
import json
from pathlib import Path
import re
import stat
from urllib.request import Request, urlopen
import zipfile

from .transaction import relative


def json_get(url):
    request = Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'commonUtils-Updater'})
    with urlopen(request, timeout=30) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError('GitHub metadata exceeds the size limit')
    return json.loads(data)


class GitHubSource:
    def __init__(self, repository, dependencies=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Expected a GitHub owner/repository')
        self.repository = repository
        self.dependencies = dependencies or {}

    def latest(self, branch):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', branch):
            raise ValueError('Invalid update branch')
        commit = json_get(f'https://api.github.com/repos/{self.repository}/branches/{branch}')['commit']['sha']
        if not isinstance(commit, str) or not re.fullmatch(r'[a-f0-9]{40}', commit):
            raise ValueError('GitHub returned an invalid commit')
        return commit

    def has_new_commits(self, current, target):
        if not re.fullmatch(r'[a-f0-9]{40}', current) or not re.fullmatch(r'[a-f0-9]{40}', target):
            raise ValueError('Invalid installed/update commit')
        comparison = json_get(f'https://api.github.com/repos/{self.repository}/compare/{current}...{target}')
        return comparison.get('ahead_by', 0) > 0

    def latest_release(self, channel, asset_name='release.zip'):
        if channel not in ('main', 'beta', 'alpha'):
            raise ValueError('Choose main, beta or alpha')
        candidates = []
        # Bounded pagination; never substitute an unclassified/draft release.
        for page in range(1, 11):
            releases = json_get(f'https://api.github.com/repos/{self.repository}/releases?per_page=100&page={page}')
            for release in releases:
                tag = release.get('tag_name', '')
                if (release.get('draft') or not release.get('published_at') or release_channel(tag) != channel
                        or channel == 'main' and release.get('prerelease')):
                    continue
                asset = next((a for a in release.get('assets', []) if a.get('name') == asset_name
                              and a.get('state') == 'uploaded' and re.fullmatch(r'sha256:[a-f0-9]{64}', a.get('digest') or '')), None)
                if asset:
                    candidates.append((release_version(tag), release, asset))
            if len(releases) < 100:
                break
        if not candidates:
            return None
        _, release, asset = max(candidates, key=lambda item: (item[0], item[1]['published_at']))
        from urllib.parse import quote
        tag = release['tag_name']
        commit = json_get(f'https://api.github.com/repos/{self.repository}/commits/{quote(tag, safe="")}')['sha']
        if not re.fullmatch(r'[a-f0-9]{40}', commit):
            raise ValueError('Invalid published release commit')
        expected = f'https://github.com/{self.repository}/releases/download/{quote(tag, safe="")}/{quote(asset_name, safe="")}'
        if asset.get('browser_download_url') != expected:
            raise ValueError('Unexpected release asset URL')
        return {'branch': channel, 'tag': tag, 'commit': commit, 'url': expected,
                'sha256': asset['digest'].removeprefix('sha256:')}

    def release_snapshot(self, release, workspace):
        from .transaction import MARKER, digest
        request = Request(release['url'], headers={'User-Agent': 'commonUtils-Updater'})
        archive_path = workspace / 'release.zip'
        total = 0
        with urlopen(request, timeout=30) as response, archive_path.open('wb') as out:
            while chunk := response.read(64 * 1024):
                total += len(chunk)
                if total > 256 * 1024 * 1024:
                    raise ValueError('Release download exceeds the size limit')
                out.write(chunk)
        if digest(archive_path) != release['sha256']:
            raise ValueError('Published release checksum does not match')
        output = workspace / 'snapshot'
        output.mkdir()
        extract_archive(archive_path, output)
        marker = output / MARKER
        manifest = json.loads(marker.read_text(encoding='utf-8'))
        files = {path.relative_to(output).as_posix(): digest(path) for path in output.rglob('*')
                 if path.is_file() and path != marker}
        if manifest.get('format') != 1 or manifest.get('revision') != release['commit'] or manifest.get('files') != files:
            raise ValueError('Published release does not match its commit/file manifest')
        marker.unlink()
        return output

    def snapshot(self, commit, workspace):
        if not re.fullmatch(r'[a-f0-9]{40}', commit):
            raise ValueError('Invalid snapshot commit')
        output = workspace / 'snapshot'
        output.mkdir()
        self._extract(self.repository, commit, output, workspace / 'application.zip')
        tree = json_get(f'https://api.github.com/repos/{self.repository}/git/trees/{commit}?recursive=1')
        if tree.get('truncated'):
            raise ValueError('GitHub returned an incomplete source tree')
        for entry in tree['tree']:
            if entry['mode'] != '160000':
                continue
            name = entry['path']
            if name not in self.dependencies:
                raise ValueError(f'Update contains an unsupported dependency: {name}')
            destination = output / relative(name)
            destination.mkdir(parents=True, exist_ok=True)
            dependency = self.dependencies[name]
            if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', dependency):
                raise ValueError('Invalid dependency repository')
            self._extract(dependency, entry['sha'], destination, workspace / ('dependency-' + entry['sha'] + '.zip'))
        return output

    @staticmethod
    def _extract(repository, commit, output, archive_path):
        request = Request(f'https://codeload.github.com/{repository}/zip/{commit}', headers={'User-Agent': 'commonUtils-Updater'})
        with urlopen(request, timeout=30) as response, archive_path.open('wb') as out:
            total = 0
            while chunk := response.read(64 * 1024):
                total += len(chunk)
                if total > 256 * 1024 * 1024:
                    raise ValueError('Update download exceeds the archive size limit')
                out.write(chunk)
        extract_archive(archive_path, output)


def release_channel(tag):
    """Numeric legacy tags and explicit main tags share the stable channel."""
    match = re.fullmatch(r'v\d+(?:\.\d+){1,2}(?:-(alpha|beta|main)(?:[.-]\d+)?)?', tag)
    return (match[1] or 'main') if match else None


def release_version(tag):
    numeric = re.fullmatch(r'v(\d+)\.(\d+)(?:\.(\d+))?(?:-(?:alpha|beta|main)(?:[.-](\d+))?)?', tag)
    return tuple(int(value or 0) for value in numeric.groups())


def extract_archive(archive_path, output):
    """Extract a single-root ZIP without links, duplicate names, or path escapes."""
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > 50000 or sum(m.file_size for m in members) > 2 * 1024 ** 3:
            raise ValueError('Update snapshot exceeds the extraction limit')
        roots = {relative(m.filename).parts[0] for m in members}
        if len(roots) != 1:
            raise ValueError('Unexpected update archive root')
        seen = set()
        for member in members:
            parts = relative(member.filename).parts[1:]
            if not parts or member.is_dir():
                continue
            name = Path(*parts)
            if name.as_posix().casefold() in seen or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Snapshot contains duplicate paths or symbolic links')
            seen.add(name.as_posix().casefold())
            if '.git' in parts:
                raise ValueError('Snapshot cannot contain Git metadata')
            destination = output / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as inp, destination.open('wb') as out:
                while chunk := inp.read(64 * 1024):
                    out.write(chunk)
            destination.chmod(0o755 if member.external_attr >> 16 & 0o111 else 0o644)
