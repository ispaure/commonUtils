# Native controls and document access

An application using these optional components can provide native destination
tabs or a wider-screen rail/sidebar, with separate Back history in each destination.
The application decides destination names, available screens and close prompts.

For images, pinch to zoom and drag to pan. At fit size, horizontal swipes ask the
application to change images. Tap asks the application to show or hide controls.
Fit returns to the centered image. The application owns image order, reading
direction and whether paging is available.

Applications can also use system document pickers. Opening a document grants
scoped access while it is being imported; the application chooses where to keep
its copy. Export asks you to choose a destination. Cancelling leaves the original
source untouched; the selected document provider controls how exported data is saved.

Native action menus show commands supplied by the application. In text editors,
Find supports previous/next matches, wrapping and optional case matching. Replace
uses literal text, including backslashes, and Replace all updates every match.
The application controls whether editing and saving are available.

[Embedding and packaging](../README.md)
