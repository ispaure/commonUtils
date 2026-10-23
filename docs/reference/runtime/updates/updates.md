# Application updates

Stdlib-only mechanisms; importing these modules performs no network or UI work.
Hosts choose repositories, channels, protected paths, settings, presentation and
cooperative shutdown. Run checks/preparation on a worker.

`GitHubSource.latest(branch)` resolves a branch commit. `snapshot(commit, workspace)`
downloads that exact source and declared pinned GitHub dependencies. This suits
applications or addons without releases. `latest_release(channel)` selects a
published, non-draft release with an uploaded `release.zip` and GitHub SHA-256
digest. Explicit `vX.Y.Z-main.N` tags and legacy numeric `vX.Y[.Z]` tags belong to main; `-beta[.N]` and `-alpha[.N]`
tags belong to their separate channels. Unknown suffixes are excluded. Selection
uses the highest numeric version in the requested channel. Main excludes
prereleases. `has_new_commits(current, target)` lets hosts avoid downgrades.

`release_snapshot(release, workspace)` verifies the asset digest and format-1
`.app-install.json` manifest: revision must match the tag commit and every managed
regular file must match its SHA-256. Extraction rejects traversal, Git metadata,
symlinks and duplicate paths and enforces download/member/expanded size limits.

`prepare_git(root, revision, protected, remote)` fetches an exact commit and pinned
initialized submodules. Tracked edits, changed submodule pins/layout, active Git
operations and private/ignored/untracked collisions abort preparation. Checkout
never uses force, reset-hard or clean. Successful updates use detached HEADs;
the host should document this to Git users. Failures restore previous commits
and unchanged local branches. Hooks are disabled for these Git operations.

`prepare_archive(root, snapshot, revision, protected)` requires a valid installed
manifest and unchanged managed files. Only those named managed files can be
replaced/deleted; new files must not collide with unmanaged files. Protected host
patterns and conservative positive `.gitignore` rules are preserved, including
nested rules. Archive negations never remove protection. Symlink paths are refused.
`apply_archive(plan, workspace)` rechecks files after shutdown and keeps rollback
copies and a recovery record outside the installation. This is a rollback
transaction, not a crash-atomic whole-tree switch; interrupted updates require
manual recovery from those records.

Copy `transaction.py` to a private staging directory outside the installation.
After the host has accepted close and stopped its workers, start it with a JSON
request containing `pid`, `plan`, `restart` (argv list) and `status` (receipt path).
It waits up to 120 seconds for the parent to exit, revalidates and applies the
plan, writes a receipt, then relaunches. Failed updates relaunch the restored
installation; rollback failures or a parent that remains alive do not relaunch.
Hosts surface failed receipts on the next startup. Preserve staging/logs for
recovery and never launch a staged request after shutdown is cancelled.

Local tests cover Git/submodule rollback, archive preservation/collisions,
release classification/checksums and detached wait/restart. Native Windows and
Linux restart launchers remain consuming-application validation responsibilities.

Channel sequence numbers accept leading zeros and sort numerically. Older clients
without `-main.N` recognition need an alpha update containing this parser or a
manual installation before they can discover explicitly numbered main releases.
