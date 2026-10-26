# Archive contents widgets

[User guide](../../../../user/archive_view/archive_view.md) · [Developer API map](../../../public-apis.md)

Passive archive entry lists, folder navigation and previews. Widgets emit requests; the application owns jobs, passwords, mutations and error presentation.

Used by Logistics Archives. Shares generic entry-selection mechanics with the file browser, while archive entries remain archive-domain data.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [__init__.py](../../../../../ui/archive_view/__init__.py) | Passive ZIP/TAR navigation and previews for Qt applications. |
| [contents.py](../../../../../ui/archive_view/contents.py) | Reusable archive contents view; navigation and presentation only. |
| [widgets.py](../../../../../ui/archive_view/widgets.py) | Archive view items and aspect-preserving image display. |

[Parent guide](../ui.md)


## Passive archive contents

`commonUtils.ui.archive_view.ArchiveContents` provides folder navigation,
filtering, numeric sorting, selection details and text/image presentation. It
accepts entries and decoded previews and emits preview/extraction/removal requests;
the owner supplies jobs and credential policy. See the [archive guide](../../archives/archives.md)
for a runnable integration outline and responsibility boundaries.
