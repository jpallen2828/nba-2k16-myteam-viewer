# Release Notes

## Card Studio Custom-Card Interchange

- Added `.2k16custom` imports from NBA 2K16 Card Studio, including the rendered card image and complete authored player data.
- Added persistent per-user custom-card storage and a **Custom cards** on/off switch. Disabling the switch hides custom cards without deleting them.
- Imported cards participate in the normal database, filters, card details, drafts, custom team builder, and live roster injection.
- Custom injection now applies authored attributes, all mapped tendencies, personality/gameplay badges, hot zones, positions, height, wingspan, weight, jersey number, handedness, loyalty, injuries, Force Non-Starter, Play Initiator, all four play types, Face ID, Portrait ID, all 45 signature selectors, and player-gear IDs.
- Signature animations use the human-readable choices preserved in the original NBA 2K16 Edit Player table and are written through their exact packed bit ranges without overwriting neighboring fields.
- Custom hot zones are re-applied after packed signature values so overlapping NBA 2K16 bitfields remain intact.
- Card Studio custom cards now keep NBA 2K16's height-proportional wingspan default (`50`) instead of treating that value as inches, and jersey number `00` remains distinct from `0` through export and injection.
- Corrected the 1989 Kenny Smith card to the Sacramento Kings franchise.
- Converted the 2013 84 OVR Roy Hibbert card to Indiana Pacers Throwback Thursday and removed the 2015 Career Connections and current Dynamic Ratings duplicates shown beside it.

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

- Added custom card artwork for the exact 1998 Historic Steve Smith, 1994 Historic Steve Smith, 1980 Historic Scott Wedman, 2005 Historic Jalen Rose, 2016 Moments Bojan Bogdanovic, 2016 Moments Austin Rivers, 2016 Playoffs Ian Mahinmi, and 2007 Rewards Michael Redd cards.
- Corrected the 1975 Bob McAdoo 94 OVR Amethyst and 88 OVR Gold cards to primary center and secondary power forward.
- Hard-coded jersey number `11` for every Elvin Hayes card and future injection.
- Added custom card artwork for the exact 1974 Historic Elvin Hayes, 2016 Playoffs Marcus Smart, 2016 Playoffs Bismack Biyombo, Dynamic Ratings Jimmy Butler (database year 2015), 2016 Playoffs Cory Joseph, 2016 Moments Matt Barnes, 2016 Playoffs Austin Rivers, and 2010 Throwback Thursday Steve Nash cards.
- Removed the 2014 Kawhi Leonard 87 OVR Gold card.
- Removed the Current/League Russell Westbrook 88 OVR Gold card and the 2013 Jimmy Butler 78 OVR Silver card.
- Removed 19 specific duplicate/unwanted cards: 2010 Paul Pierce (89), 2010 Rajon Rondo (87), 1989 Sidney Moncrief (87), 2010 Deron Williams (86), 1994 John Stockton (86), 2010 Carlos Boozer (85), 1989 Michael Cooper (85), 1993 James Worthy (84), 2013 Paul George (84), 2010 James Harden (83), 1989 James Worthy (83), 1993 Terry Cummings (83), 1989 Terry Cummings (83), 1989 Dennis Johnson (82), 2013 Kawhi Leonard (82), 1994 Dan Majerle (82), 1986 Larry Nance (82), 2013 Brandon Jennings (80), and 2010 Jason Richardson (80).
- Updated the card artwork for only the 2016 89 OVR Austin Rivers, 2010 90 OVR Steve Nash, 2001 90 OVR Vlade Divac, and 1982 90 OVR Robert Parish cards.
- Removed the 1994 Patrick Ewing 90 OVR Amethyst card from the card database.
- Updated every Spencer Haywood card to use face and portrait ID `2886`.
- Updated Sam Cassell's Minnesota Timberwolves and Boston Celtics cards to jersey number `19`.
- Updated only Greg Anthony's Memphis Grizzlies card to jersey number `2`.
- Corrected card `358` from Steve Nash to Ben Gordon, assigned it to `UNASSIGNED`, and set jersey number `7`.
- Removed the duplicate bronze Jonathan Simmons card that used jersey number `0`; the separate jersey-`17` card remains available.
- Updated the 2013 Patty Mills card to jersey number `8`.
- Updated every Jeff Taylor card to jersey number `44`.

### Installation

See the "Installing the College-Team Compatibility Roster" section in `README.md`.
