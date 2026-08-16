# NBA 2K16 Card Studio

NBA 2K16 Card Studio is a standalone Windows desktop application for composing cards and authoring complete custom NBA 2K16 players. It has its own executable, settings, projects, build, and tests, while its optional `.2k16custom` export imports directly into the NBA 2K16 MyTEAM Viewer.

Current version: **0.11.3 — live position-specific OVR, complete Viewer-aligned presets, and verified Chasedown Artist support**

The authored Player Name and four-digit Season/year are separate from the searchable **Import data from existing card** field. Choosing a parent card imports its editable gameplay data, jersey number, face/portrait identity references, signatures, tendencies, badges, and hot zones without replacing the custom card title or year. A leading card-title year such as `'21` or `'89` synchronizes to 2021 or 1989. Exported custom cards use stable positive IDs.

The permanent built-ins are **Bronze**, **Silver**, **Gold**, **Amethyst**, **Diamond**, and **Pink Diamond**. Each uses a native 325 × 455 transparent frame and dynamic text containers. Card Studio does not use generative AI, generative fill, or automatic copyrighted-asset downloads; cleanup uses deterministic masks and authentic source pixels.

Choose a tier from the always-visible **Card tier** dropdown. The rarity order is Pink Diamond, Diamond, Amethyst, Gold, Silver, Bronze. Selecting another tier swaps the frame while retaining the imported player image, entered card text, and the exact player X, Y, scale, rotation, and horizontal-flip values.

## Simple card workflow

Everything needed for normal card creation is visible in one workspace:

- Choose an installed tier from **Card tier**.
- Select **Import Image** and choose player artwork.
- For an opaque photo, choose **Remove Background** to create a local transparent cutout. The original image remains available and is not replaced while analysis runs.
- Enter **OVR**, **Position**, and **Player Name** in the Card Text panel. Values normalize to uppercase and update the native-resolution preview immediately.
- Choose **Current**, **Historic**, or **EuroLeague** under **Logo set**, then select a team logo. **No logo** removes it. Team logos use the fixed source-card placement and are not manually resized.
- Choose one of the recovered **Card background** textures, or **No background** for a transparent center.
- Choose a **Promotion logo** for the authentic bottom-left sticker position, or **No promotion logo**.
- Select **Delete PNG**, or focus the card canvas and press Delete, to remove the imported player. Undo restores it.
- Drag the player on the card or adjust the visible **X** and **Y** controls. Arrow keys nudge one pixel; Shift+arrow nudges ten. Hold Ctrl and use the mouse wheel for gradual 1% resize steps, or type an exact value in **Player size** at the top (5.00%–500.00%).
- Use **Undo** and **Redo** for card edits.
- Use **Save Project** for an editable `.2k16card` file and **Open Project** to resume one.
- Use **Export PNG** for the finished native-size RGBA card.
- Select **Edit Attributes** to edit Vitals, all 61 recovered attributes, all 84 tendencies, signature animations, personality and tiered gameplay badges—including Chasedown Artist—and hot zones. The Player Data header shows the live position-specific OVR with two decimal places on every tab. **Done** returns to the card workspace.
- Use **Export Card + Data** to create a `.2k16custom` package containing the PNG and complete player data for the MyTEAM Viewer.

## Custom player data

The player-data workspace follows the recovered NBA 2K16 player-record order and grouping. Its searchable **Player name** selector contains the complete current Viewer preset database, disambiguated by season, OVR, and franchise. Choosing an entry fills its known card ratings, tendencies, badges, hot zones, identity data, and verified roster-derived signature animations; every populated control remains editable. Theme and Collection are synchronized dropdowns built from the Viewer taxonomy, with collections narrowed to the selected theme.

The editor also includes name, season, overall, tier, franchise, primary and secondary position, height in feet/inches, weight, age, origin, jersey number (including distinct `0` and `00` choices), handedness, Face ID, Portrait ID, loyalty, both injury slots and durations, Force Non-Starter, Play Initiator, and all four play types. Attribute values use the game’s 25–99 range; tendencies use 0–100. Personality badges are on/off, while gameplay badges offer None, Bronze, Silver, and Gold. Wingspan is no longer exposed as inches: custom cards retain NBA 2K16’s default height-proportional wingspan value of `50`.

### Position-specific overall calculator

The Player Data header calculates OVR from primary position, authored height, the 43 performance ratings, and the 16 body-part durability ratings. It displays the primary position and continuous score to two decimal places beside **Player Data**, remains visible on every tab, and updates immediately when any verified input changes. The card's integer Overall field is synchronized automatically to the nearest whole number.

Version 2 was calibrated against NBA 2K16's native live recalculation routine. The recovered runtime structure takes the maximum of nine position-specific, clamped category scores and includes position-specific height suitability plus the game's rounded hidden durability aggregate. It reached 100% exact displayed-OVR agreement on both a 500-sample post-refinement all-band live holdout and a separate 3,000-sample 60–79 live holdout (600 per position), with 100% within one point. On all 2,234 untouched live-roster players it also exceeds 99.8% exact and remains 100% within one point. Weight, wingspan, secondary position, potential, emotion, badges, hot zones, tendencies, signature animations, and play-initiator state were excluded after controlled tests produced no cache change.

The inspectable runtime model is `assets/player_database/overall_formula_v2.json`. The original MyTEAM-derived Version 1 asset remains at `assets/player_database/overall_models.json` for rollback and developer comparison. Run `python tools/compare_overall_versions.py` for compact fixture diagnostics.

All 45 signature selectors use the human-readable choices preserved in the original NBA 2K16 Edit Player table, grouped as Jump Shooting, Layups & Dunks, Post Game, Ball Handling, and Misc. Compact internal dunk names are separated into readable English words while retaining their exact game IDs. Packed fields are written bit-by-bit so neighboring animations are preserved. Hot zones use Cold, Neutral, and Hot and are applied after packed signature fields so their shared bits remain correct. The Player Gear editing tab was removed; existing gear values in older project files remain preserved for compatibility.

The `.2k16custom` package is separate from editable `.2k16card` project files. PNG-only export remains available. A data package carries the authored attributes, tendencies, badges, hot zones, signatures, gear, identity fields, and appearance measurements. In the Viewer, choose **Import custom card**; the **Custom cards** switch controls whether imported cards appear in the collection and lineup tools.

## Local player background removal

The official Card Studio ZIP packages **BiRefNet General Lite (Swin-v1-tiny, epoch 232)** as `models/player_background_removal.onnx`. It runs entirely through ONNX Runtime without an online service. CPU inference is the universal packaged backend. The service can select an installed DirectML, CUDA, ROCm, or OpenVINO provider in development environments, but the portable Windows package does not require any GPU runtime. The 214 MB ONNX file exceeds GitHub's normal per-file limit and is therefore omitted from the repository source tree; copy it from the official Card Studio ZIP when building the complete portable package.

The feature is non-generative. Inference creates only a grayscale alpha mask. Card Studio constructs the cutout from the original imported RGB pixels plus that mask; it does not repaint, enhance, recolor, sharpen, or repeatedly resample the player source. The ONNX session is loaded lazily and cached. Analysis runs in a background worker with visible stages, cancellation checkpoints, and request identity checks that prevent a late result from replacing a newer import.

After analysis, **Accept Cutout** uses the mask immediately, **Refine Mask** opens the focused correction controls, **Retry** runs automatic segmentation again, and **Restore Original** removes the accepted mask. Refinement provides Restore Subject and Remove Background brushes, soft/hard edges, size and strength, per-stroke Undo/Redo, reset to the automatic mask, original/cutout/mask/red-overlay views, checkerboard transparency, wheel zoom, middle-mouse pan, Fit, Actual Pixels, and conservative threshold/softness/erosion/dilation/island controls.

Accepted and automatic masks are stored losslessly as compressed grayscale PNG data inside `.2k16card` projects together with model/version, edge settings, and the manual-edit flag. Reopening uses the saved mask without rerunning inference. A relinked original receives the saved mask only when its dimensions match.

Model metadata and the required SHA-256 integrity hash are in `models/model.json`; the upstream MIT text is distributed as `models/LICENSE-BiRefNet.txt`. If either the model or metadata is missing, corrupt, or incompatible, Card Studio reports the problem and leaves ordinary image importing operational.

The simplified interface intentionally omits layer diagnostics, mask previews, manual zoom controls, template validation tools, external-template browsing, and the multi-source Template Builder. Rotation, horizontal flip, and reset controls are also hidden. Scale remains available through the exact **Player size** percentage field and Ctrl+mouse-wheel, and existing advanced transform values remain preserved when a project is opened and saved.

## Bundled team logos

Card Studio packages 102 recovered logo PNGs under `assets/team_logos`: 31 Current choices (including NBA Free Agency), 46 Historic choices, and 25 EuroLeague choices. The source PNG bytes are preserved exactly; `manifest.json` records every source path, SHA-256 hash, native size, mode, and alpha status. The two source `Contact Sheet.png` overview images are intentionally excluded because they are not individual team logos.

The selected category and logo are saved in `.2k16card` projects and participate in Undo/Redo. Manual team-logo resizing was removed after registration against the saved 325 × 455 cards. The recovered transform renders the square logo canvas at 351 × 351 with origin `(72, -50)`, then clips it to the tier's card-art opening.

## Recovered card backgrounds and promotion logos

The **Card background** menu contains all 11 PNGs supplied under `assets/myteam_card_backgrounds/png`: 99 Club, Consumable, Current, Dynamic, EuroLeague, Historic, Moments, Playoffs, Rewards, ROTY/DPOY, and Throwback. The original 1024 × 1024 pixels are kept unchanged. At render time a working copy is reduced to the game's 512 × 512 card square and centered over the native 325 × 455 canvas, producing the verified crop at approximately `(-94, -28)`.

The **Promotion logo** menu contains all 13 normalized PNGs supplied under `assets/myteam_promotion_logos/runtime/normalized`, including USA Olympics. Their recovery manifest supplies readable names, and source-card extraction measurements restore the normalized images to their original differing apparent sizes in the bottom-left cluster. Promotion stickers render above the player and other artwork.

The selected promotion logo is also authoritative custom-card metadata. Card Studio automatically synchronizes the exported Viewer theme and collection with the visible sticker: Current and Dynamic Ratings use the selected team collection, Historic uses that team's Franchise collection, Throwback uses its team Throwback Thursday collection, and award/event stickers use their corresponding official MyTEAM grouping. A valid more-specific selection such as `Playoff Moments: Finals` is preserved.

The artwork depth used by preview and export is: recovered background, template background, team logo, tier frame, clipped player cutout, dynamic text, then promotion sticker. This preserves the source-card evidence that the team emblem is beneath the frame and player while the promotion sticker is the top artwork layer. Background, team-logo, promotion-logo, and tier selections are all persisted and undoable.

Player cutouts may overlap the full width of the tier frame, including the thick left rail, matching authentic cards where arms, balls, and trophies cross that border. The bottom nameplate remains protected from player artwork.

## Authentic dynamic text

OVR, position, and player-name text is rendered from packaged RGBA bitmap glyphs extracted at native resolution from authentic NBA 2K16 card images. Final rendering does not use an installed font, browser text, internet service, or original source-card file. The three independent atlases are in `assets/text_styles/nba2k16_default` and cover A–Z, space, period, hyphen, apostrophe, digits 0–9, and the OVR label. `extraction_report.json` records source references, approval state, and missing coverage (currently none).

Names are normalized to uppercase, measured with source-derived advances and observed pair kerning, tightened from preferred tracking to the tier's safe minimum, and then uniformly scaled only when needed. The atlas builder rejects outlier crops by selecting a deterministic alpha medoid from the dominant native crop geometry. Fully transparent extraction padding is excluded from optical centering. Text is omitted with a visible warning if an authentic glyph is unavailable or a value cannot fit above the tier's minimum scale; it is never replaced with an unrelated font or drawn as partial clipped letters. OVR, position, and name placement for all six tiers comes from each tier's own `template.json` safe region, baseline, tracking, scale, and centered alignment metadata.

Bronze, Silver, and Gold apply a subtle one-pixel black bitmap shadow behind both the dynamic OVR label and rating to retain readability on their light tier panels. The darker Amethyst, Diamond, and Pink Diamond panels keep the unshadowed source-derived glyphs.

The OVR label and numeric rating share the same optical horizontal center in every built-in tier, including ratings whose glyph widths have different odd/even pixel parity.

OVR glyph extraction retains the connected bright glyph component and rejects disconnected player or card-art pixels inside the crop. The digit `1` uses an unobstructed authentic Steve Nash source crop, replacing the earlier George Lynch crop in which a hand overlapped the rating panel.

`.2k16card` projects persist all three values, the selected text style, fitted scale/tracking results, and optional text offsets. Preview and export call the same renderer and rebuild from the original atlas pixels on every render.

### Glyph-atlas development tool

The internal deterministic tool can rebuild all approved atlases and their preview/report without modifying source cards:

```powershell
python tools\glyph_atlas_tool.py build-auto
```

`extract-one --help` exposes manual source import, glyph role, native crop rectangle, character assignment, baseline, left/right bearings, vertical offset, advance, plate-removal floor, duplicate comparison, and explicit duplicate approval. Candidate metadata stores source paths and hashes. The source cards are development inputs only and are not bundled by the executable.

The Template Builder source code, tests, Diamond extraction script, and `.2k16templatework` format remain in the development tree; they are not exposed in the normal application interface. They can be restored later without discarding the Diamond extraction work.

The project formats remain separate:

- `.2k16card` stores one Card Editor composition and references a tier plus external player artwork.
- `.2k16templatework` stores a versioned Template Builder session: external source paths, transforms, compressed editable masks, regions, patches, manual pixels, settings, history descriptions, viewport state, timestamps, and output location. Full source images are not embedded or altered.

## Install, run, test, and build

Python 3.12 or later is recommended. From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m app.main
```

You can also run `run_card_studio.bat` after installing dependencies.

OpenCV performs deterministic registration and perspective transforms. Pillow and NumPy handle lossless image loading, compositing, masks, diagnostics, and exports.

Run the deterministic test suite (tests use the packaged raster glyph assets, not the original source cards):

```powershell
python -m pytest
```

To build the complete standalone Windows GUI package, first copy `models\player_background_removal.onnx` from an official Card Studio ZIP into this source tree, then run:

```powershell
.\build_card_studio_release.ps1
```

The canonical output is `release\NBA.2K16.Card.Studio.zip`.

## Advanced Template Builder reference (not exposed in the simplified UI)

The sections below document the retained development implementation. These commands and tabs are not present in the streamlined application.

### Begin a new authentic tier

1. Open Card Studio and choose **Template Builder**.
2. Press **Ctrl+N**. Enter the tier name, a lowercase template ID, and a working width and height.
3. Prefer the exact dimensions of a cropped reference card. Alternatively enter a verified size or match an existing template. A scaled screenshot does not prove the game's original internal asset resolution, so leave the status as `working` unless verified.
4. Use **Import…** or **Source Cards > Import Source Cards** and select several cards from the same tier. PNG, WEBP, TIFF, BMP, and JPEG are accepted; JPEG receives a lossy-compression warning.
5. Card Studio reports dimensions, mode, alpha, alignment state, duplicate file/pixel content, likely crop differences, and warnings. A mismatched source stays disabled until you deliberately normalize it.

Several same-tier cards are useful because players, names, positions, ratings, and logos vary while authentic frame pixels repeat. More genuinely different sources can increase confidence in shared pixels.

### Normalize and align sources

Select a source in the left panel. **Crop / four corners** offers rectangular crop or explicit four-corner perspective mapping to the working canvas. The original source remains untouched. Translation, rotation, scale, reset, and optional subpixel resampling are stored as transform metadata.

Choose the cleanest normalized source as the reference. Paint the `alignment` mask over stable border details; its default is a hard-edged outer frame that reduces influence from central player/text content. **Propose automatic alignment** uses deterministic phase correlation plus constrained OpenCV registration. It displays method, transform, score, and warnings before anything is accepted. Integer X/Y alignment is the default. Subpixel mode can improve geometric fit but resamples pixels, so use it deliberately.

Arrow keys nudge the selected source one native pixel; Shift+arrow nudges ten. Overlay, adjustable opacity, flicker, split, absolute/amplified difference, and source-only views help review alignment.

### Candidate composites and diagnostics

The Composite tab provides:

- Per-channel median
- Per-channel trimmed mean
- Most common exact RGBA
- Most common RGB with separately analyzed alpha
- Lowest-variance source selection
- User-ordered source priority
- Configurable consensus threshold

Methods are deterministic. A named mask can override the global method for a region. **Generate / Refresh** runs analysis on a worker thread with an operation generation number, so a stale result cannot replace newer work. The operation can be cancelled.

The canvas includes candidate, variance, consensus, alpha, and provenance views. Cursor readouts show the native X/Y plus reference, selected, candidate, and final RGBA. At high zoom, the pixel grid maps edits to integer card pixels.

Consensus is the fraction of sources exactly agreeing with the selected candidate pixel. Variance measures per-channel spread. High/medium/low display classes are configurable diagnostics—not proof that a pixel is authentic or “pixel-perfect.” Diagnostic colors never enter exported layers.

### Masks, blank areas, patches, and pixels

Builder projects include named masks for alignment, stable frame, variable exclusion, player art, foreground, background, overall text, position text, player name, logo, protected pixels, and unresolved pixels.

Select a mask, alpha, and exact integer brush size. Use brush, eraser, rectangle, ellipse, flood fill, coordinate-defined polygon, invert, fill, or clear. Masks are hard-edged by default. Feathering happens only when **Apply feather** is pressed with a nonzero radius.

Use these masks to mark variable player/text/logo content, stable border pixels, and locations that no source can reliably supply. Paint `background` where pixels must render behind the player and `foreground` where border lips/decorations must cover the player. Paint `player_art` as the clipping mask: white permits the player, black hides it, and grayscale supplies partial alpha.

For authentic cleanup:

- Choose **Source patch** and an imported source. Left-drag copies the same coordinates into the working result by default. An explicitly enabled X/Y offset visibly changes the sampled source coordinate. Every patch is non-destructive and records source provenance.
- Choose **Manual pixel** for final one-pixel RGBA corrections. Pick RGBA from the selected source, reference, or candidate under the cursor, or choose a value manually. Right-drag erases manual overrides. Manual pixels are tracked separately and cause an export warning because they lack source provenance.
- Paint the `unresolved` mask where no trustworthy authentic source exists. The application never fills such areas by invention.

Continuous canvas strokes are grouped as one history action. Source transforms/removal/reordering, masks, patches, pixel edits, text regions, layer assignments, composite settings, and region overrides can be undone/redone through the History tab or Ctrl+Z/Ctrl+Y.

### Text regions and layer-depth testing

The Text Regions tab defines `overall`, `position`, and `name` rectangles. Each stores X/Y/width/height, optional baseline, horizontal/vertical alignment, maximum width, expected color placeholder, clean state, notes, and the reference source. Phase 2 records blank plates and coordinates only; it does not infer fonts or draw final text.

The Finalize tab can load a temporary sample-player PNG for background/player/foreground depth inspection. This image is held only for preview and is never embedded in exported tier assets.

### Save, autosave, and recovery

Use Ctrl+S to save `.2k16templatework`. Existing valid saves receive timestamped backups before replacement. A configurable autosave interval (default three minutes) writes a separate crash-recovery file. Card Studio offers recovery on the next launch and never overwrites imported sources.

Writable files are isolated under:

```text
%LOCALAPPDATA%\NBA2K16CardStudio\
|-- projects\
|-- builder-projects\
|-- builder-autosaves\
|-- builder-backups\
|-- exports\
`-- logs\
```

Set `NBA2K16_CARD_STUDIO_DATA_DIR` to use an isolated development/testing location. Qt settings use organization `NBA2K16Tools` and application `NBA2K16CardStudio`.

### Finalize and export a tier

1. Assign background, foreground, and player-mask pixels.
2. Define and review all three text regions.
3. Inspect candidate, final, alpha, unresolved, and provenance views.
4. Select **Run final validation**.
5. Structural errors (invalid ID/dimensions, missing sources/candidate, mismatched layers) block export. Warnings (unresolved pixels, missing/unclean text regions, empty layers, empty/full mask, missing source references, manual pixels, or overwrite) require explicit confirmation.
6. Select **Export v2 template package**, choose the templates root, and optionally load the result immediately in Card Editor.

The package is:

```text
<template_id>\
|-- background.png
|-- player_mask.png
|-- foreground.png
|-- template.json
|-- preview.png
`-- diagnostics\
    |-- consensus.png
    |-- variance.png
    |-- unresolved.png
    |-- provenance.png
    `-- extraction_report.json
```

Runtime layers are exact-size lossless PNGs; diagnostics are not listed as render layers. The JSON report records measurable counts, methods, source filenames, alignment methods, dates, and versions without claiming pixel-perfect extraction. Phase 1 version 1 templates remain supported alongside Builder-exported version 2 templates.

## Card Editor summary

Card Studio loads native-size background/player-mask/foreground layers, imports player art, uses a bottom-center anchor, exposes X/Y positioning and Ctrl+wheel scaling, clips the player, saves `.2k16card`, and exports exact-size RGBA PNG. Template layers are never silently resized.

## Keyboard shortcuts

- Ctrl+N: new project for the active workspace
- Ctrl+O: open the active workspace's project format
- Ctrl+S / Ctrl+Shift+S: save / save as
- Ctrl+I: import player art
- Ctrl+Shift+R: remove/refine the imported player's background
- Ctrl+Shift+I: import Builder source cards
- Ctrl+E: export the finished PNG
- Ctrl+Shift+E: finalize/export Builder package
- Ctrl+G: generate Builder composite
- Ctrl+Z / Ctrl+Y: Builder undo / redo
- Arrow / Shift+arrow: nudge the player by 1 / 10 pixels
- Ctrl+mouse-wheel: resize the imported player image gradually (1% per wheel notch)
- Delete while the card canvas is focused: remove the player image; Ctrl+Z restores it
- Ctrl++ / Ctrl+-: zoom in / out
- Ctrl+0 / Ctrl+1: fit / actual pixels

## Current limitations

The Diamond extraction is derived from one authentic supplied card, but it is not a claim of complete or pixel-perfect recovery behind occlusions. OpenCV proposals still require visual confirmation, especially for compressed, cropped, low-detail, or resampled screenshots. Polygon input uses explicit coordinate entry.

Automatic segmentation is not guaranteed to be perfect. Similar foreground/background colors, translucent or reflective edges, motion blur, fine hair, fingers, and narrow gaps may require Restore Subject or Remove Background brush correction. Cancellation is safe at Card Studio's checkpoints and prevents results from being applied, but ONNX Runtime may finish the currently executing CPU graph before the worker exits.

Dynamic text is complete for the packaged Bronze, Silver, Gold, Amethyst, Diamond, and Pink Diamond tiers. Names support A–Z, 0–9, spaces, apostrophes, periods, and hyphens. Card collection/auction features, online accounts, cloud storage, and companion-app integration remain intentionally absent. Custom position letters outside the stock PG/SG/SF/PF/C set reuse the authentic native-size condensed nameplate glyph for that character; stock labels use position-badge extractions.

## Built-in Diamond extraction

The completed Diamond extraction is stored in `templates/diamond` and byte-copied into the runtime package at `assets/built_in_templates/diamond`. The reproducible extraction script is `tools/extract_diamond_template.py`.

Only `data/card-images/9857-kareem-abdul-jabbar.png` was used. The source was hash-checked and never modified or resized. The OVR label, rating, and position glyph were removed with deterministic masked cleanup from their own surrounding source pixels. The permanent beveled divider below the OVR rating is protected from cleanup and restored from the exact source coordinates. The player name was replaced by a mirrored clean nameplate texture from the same source, beginning to the right of the protected Diamond corner.

The background layer is fully transparent. The foreground contains only the preserved left rail and bottom frame, while `player_mask.png` opens the center for imported player art. The package includes an unresolved map, color provenance view, measurable JSON report, human-readable notes, and a compressed source-coordinate map. Hidden center artwork is marked unresolved and omitted rather than guessed.

Pink Diamond preserves the user-supplied transparent frame and uses the same authentic neutral three-row OVR divider at the same native coordinates as Diamond. Only the divider pixels are transferred; the surrounding Pink Diamond panel remains unchanged.

## Bronze, Silver, Gold, and Amethyst extractions

The six runtime packages live under `assets/built_in_templates`. `tools/extract_standard_tiers.py` verifies each attached source hash and native dimensions, preserves the original rail/frame coordinates, removes text with source-based deterministic cleanup, clones only clean native nameplate texture, and makes every card-specific center pixel transparent. It also installs the maintained Diamond and Pink Diamond packages. Original source cards are neither copied into the runtime folders nor bundled into the executable.
