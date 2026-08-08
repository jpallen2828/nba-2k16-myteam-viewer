# NBA 2K16 MyTEAM Viewer v1.1.1

This patch updates **Create a random team** so all six card tiers have an equal chance of appearing.

## Changes

- Enabled custom cards now participate in random teams, including Pink Diamonds.
- Each position first rolls uniformly among Pink Diamond, Diamond, Amethyst, Gold, Silver, and Bronze, then selects a random eligible card from that tier.
- Removed the previous per-card weighting, guaranteed Amethyst/Diamond slot, and one-Bronze limit.
- The lineup still contains one primary-position PG, SG, SF, PF, and C with no duplicate player names.
- Added regression tests covering all six tiers at every position and tier probability independent of pool size.

The release also includes the unchanged **NBA 2K16 Card Studio v0.9.2** companion ZIP and updated SHA-256 checksums.

Extract the Viewer ZIP before running it. Existing imported custom cards remain stored in the current Windows user's local application-data library.
