# NBA 2K16 Card Studio 0.11.3

NBA 2K16 Card Studio is the companion creator for the MyTEAM Viewer. It makes finished card artwork and can package that artwork with complete authored player data for browsing, drafting, lineup building, and roster injection in the Viewer.

The public source, tests, templates, and distributable art libraries are available in the repository's [`card-studio/`](card-studio/) directory.

## Install

1. Download `NBA.2K16.Card.Studio.zip` from the project's [latest GitHub release](https://github.com/jpallen2828/nba-2k16-myteam-viewer/releases/latest).
2. Extract the entire ZIP to a normal local folder. Do not run the program from inside the ZIP.
3. Keep `NBA2K16CardStudio.exe` and the included `models` folder together.
4. Run `NBA2K16CardStudio.exe`.

The app is portable and does not need an installer. It is an unsigned fan-made Windows application, so SmartScreen or Windows Security may show a warning. Only allow it if you downloaded it from the official project release and trust the published source and checksums.

## What it does

- Creates Bronze, Silver, Gold, Amethyst, Diamond, and Pink Diamond cards at 325 × 455 pixels.
- Imports player artwork and provides non-destructive position, scale, and horizontal-flip controls.
- Removes image backgrounds locally with the included BiRefNet ONNX model; no cloud service or generative image editing is used.
- Provides Current, Historic, and EuroLeague team logos, 11 recovered MyTEAM backgrounds, and 13 promotion stickers including USA Olympics.
- Renders OVR, position, and player name with packaged game-derived bitmap glyphs.
- Edits vitals, all supported attributes and tendencies, signatures, every verified personality and gameplay badge—including Chasedown Artist at Bronze, Silver, or Gold—hot zones, identity IDs, play types, and related custom-player fields.
- Imports an official Viewer card as an editable starting point without replacing the custom name or season.
- Saves editable projects, exports transparent PNG artwork, and exports complete Viewer-ready card packages.

Card Studio does not inject rosters itself. The MyTEAM Viewer performs roster injection after a custom package is imported.

## Create a card

1. Choose a rarity under **Card tier**.
2. Select **Import Image** and choose a player image.
3. If the image has an opaque background, select **Remove Background**. Accept the automatic cutout or use **Refine Mask** to restore subject pixels and remove remaining background pixels.
4. Set the OVR, position, and player name.
5. Choose the logo set and team logo.
6. Choose a card background and promotion logo. The promotion selection also determines the Viewer's theme and collection when exported.
7. Drag the player on the canvas. Use the X/Y controls, arrow keys, **Player size**, or Ctrl + mouse wheel for precise placement.
8. Select **Edit Attributes** to author or review the complete player data.
9. Save an editable project if you may want to revise the card later.
10. Export either a finished PNG or a complete card-and-data package.

## Player-data workflow

The searchable existing-card selector can populate a card from one of the Viewer's official player entries. It is useful as a starting point for ratings, tendencies, badges, signatures, identity IDs, and hot zones. After importing a preset, every populated field remains editable and the authored player name and season stay independent.

Review the following before export:

- Name, season, OVR, tier, franchise, theme, and collection
- Primary and secondary position, height, weight, age, origin, and jersey number
- Face ID, portrait ID, handedness, loyalty, injuries, starter/play-initiator options, and play types
- Attributes, tendencies, signature animations, badges, and hot zones

For a new real player, choose the closest verified parent player where appropriate and then adjust the authored fields. Exact custom facial sculpts require a separately verified live-game capture; ordinary Card Studio fields cannot invent those linked bytes.

## File types

| Extension | Purpose |
| --- | --- |
| `.2k16card` | Editable Card Studio project. Reopen it to change artwork, layout, text, or player data. |
| `.png` | Finished card artwork only. It does not contain injectable player data. |
| `.2k16custom` | Portable card artwork plus authored player data for MyTEAM Viewer. |

## Import into MyTEAM Viewer

1. Open `NBA 2K16 MyTEAM Viewer.exe`.
2. Choose **Import custom card**.
3. Select the exported `.2k16custom` file.
4. Keep **Custom cards** enabled to show imported cards.
5. Find the card in its authored theme and collection, or use the custom-only filter.
6. Open the card details and verify its artwork, OVR, position, ratings, tendencies, badges, and hot zones before injection.

Imported packages are copied into the current Windows user's local application-data folder. Replacing the portable Viewer with a newer release does not delete that personal library. Cards bundled with the public release are also included directly in the Viewer package.

## Background-removal model

The portable ZIP includes `models/player_background_removal.onnx`, its metadata, and its license. The model creates only an alpha mask; Card Studio keeps the original RGB pixels. The model runs locally and can be slow on CPU during the first analysis. Removing or separating the `models` directory disables background removal but does not affect ordinary image importing and manual composition.

## Updating

Extract a new Card Studio release to a fresh folder, then open existing `.2k16card` projects normally. Keep personal projects and exports outside the application folder when possible. Update the Viewer separately using its own ZIP; the two applications intentionally remain independent.

## Legal notice

This is an independent, non-commercial fan tool. It is not affiliated with or endorsed by 2K, Take-Two, the NBA, the NBPA, or any other rights holder. It does not include NBA 2K16 executables, DLLs, or archive containers.
