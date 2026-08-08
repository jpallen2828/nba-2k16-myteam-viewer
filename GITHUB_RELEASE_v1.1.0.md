# NBA 2K16 MyTEAM Viewer v1.1.0 + Card Studio v0.9.2

This is the largest project update since v1.0.7. The release now includes two separate portable Windows apps that work together:

- **NBA.2K16.MyTEAM.Viewer.zip** — browse the archive, build and draft lineups, import custom cards, and inject teams into a locally loaded NBA 2K16 roster.
- **NBA.2K16.Card.Studio.zip** — create card artwork, author complete player data, and export `.2k16custom` packages for the Viewer.

Extract each ZIP before running it. Card Studio must stay beside its included `models` folder.

## Highlights

- Added Card Studio 0.9.2 as an official companion download with local background removal, six authentic card tiers, team/promotion artwork, editable projects, complete player-data authoring, and Viewer-ready exports.
- Added secure and persistent `.2k16custom` imports to the Viewer, custom-card visibility controls, custom-only filtering, and full integration with details, drafts, teams, saved lineups, and injection.
- Added Pink Diamond as a tier above Diamond with separate mode- and round-specific draft odds.
- Bundled 55 complete custom cards and their exact artwork, including the latest Dirk Nowitzki, Andrei Kirilenko, Kawhi Leonard, Stephen Curry, LeBron James, Joel Embiid, and Luka Doncic cards.
- Added the first verified exact custom-sculpt injection workflow. The Luka card carries a captured 52-byte sculpt block and 132-byte CAP appearance block, written through destination-owned pointers and verified after injection.
- Updated Joel Embiid to the scanned 96 OVR roster data and finished MVP card artwork.
- Added expanded college-team injection through the included compatibility roster.
- Added safer import paths, parent-template selection, same-name gear inheritance, player-name normalization, cached-overall writes, linked appearance verification, and extensive regression tests.
- Moved generated Viewer files into the hidden project area so the public app folder stays clean.
- Corrected Jerry West's height and removed six unwanted database entries.

## Install and update

1. Download the Viewer ZIP and extract it to a normal local folder.
2. Download and extract Card Studio separately if you want to create custom cards.
3. Keep the complete contents of each extracted folder together.
4. Start NBA 2K16 and load the intended roster before using Viewer injection.
5. Existing personally imported Viewer cards remain in the current Windows user's local application-data library after replacing the portable Viewer folder.

See `README.md`, `CARD_STUDIO.md`, and `RELEASE_NOTES.md` inside the Viewer ZIP for complete instructions and patch notes. `SHA256SUMS.txt` provides checksums for both release archives.

This is an independent, non-commercial fan project and is not affiliated with or endorsed by 2K, Take-Two, the NBA, or the NBPA. No NBA 2K16 executable, DLL, or archive container is included.
