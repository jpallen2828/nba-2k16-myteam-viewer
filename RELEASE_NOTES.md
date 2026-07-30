# Release Notes

## College-Team Injection Update

### New

- Added injection destinations for Kansas, Georgetown, Arizona, Louisville, UCLA, Connecticut, Texas, Michigan, Villanova, and Wisconsin.
- Added support for the expanded compatibility roster: nine college teams have 15 player destinations and Louisville has 14.
- Added the custom `Myteam Compatibility roster` file to the public release ZIP.
- Added direct NBA, Historic, and College destination controls to the roster-injection interface.

### Safety and Repeat Injection

- College injection now validates stable live `TEAMDATA` labels, IDs, player counts, and player-pointer topology before writing.
- Compatibility validation does not depend on original player names, allowing the same roster to be injected repeatedly.
- Injection tracking now records exact destination roster indices so later overwrites use the correct noncontiguous college slots.
- Position writes preserve hidden/generated-player flag bits.
- Removed the extra browser confirmation popup; compatibility is checked automatically.

### Player Data Corrections

- Updated every Spencer Haywood card to use face and portrait ID `2886`.
- Updated Sam Cassell's Minnesota Timberwolves and Boston Celtics cards to jersey number `19`.
- Updated only Greg Anthony's Memphis Grizzlies card to jersey number `2`.

### Installation

See the “Installing the College-Team Compatibility Roster” section in `README.md`.
