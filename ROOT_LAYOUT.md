# Root layout decisions

The pre-change documentation checkpoint is tagged `commonUtils-Pre-Refactor`.

Large standalone public modules become same-named packages, keeping imports,
class identities and feature reference strings stable. Their __init__.py holds
the existing implementation; this pass does not split classes or change policy.
Every package has a README describing its entry points.

Related mechanisms have one canonical implementation: filesystem transfers,
removal, traversal and network policy live under filesystem; ZIP streaming lives
under archives; shared UI settings live under configuration; downloading lives
under streams. Historical import packages alias those canonical module objects
so monkey-patches and caches remain shared. Consumers can migrate gradually.

Root Python files are limited to package metadata, configUtils.py (unchanged),
and four existing compatibility shims: directory_index, text_files, session_store
and pySideUtils. Cross-cutting contributor, license and user guides stay at root;
folder READMEs own local API explanations and link to those guides as needed.

The relocation changes relative imports and the two source-relative paths in
fileUtils.get_current_working_dir and configuration.settings.settings_path.
Their resolved locations remain unchanged. Application caches and data files
have not moved.
