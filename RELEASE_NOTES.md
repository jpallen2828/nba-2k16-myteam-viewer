# Release Notes

## Promotion-logo theme and collection synchronization - August 7, 2026

- Custom cards now carry their selected bottom-left promotion-logo ID into the Viewer package.
- Older custom-card packages that lack `promotionLogoId` now infer the promo from the embedded card PNG, so the visible sticker still controls the imported theme and collection.
- Import automatically assigns the matching official Viewer theme and collection, using the selected franchise for Current, Dynamic Ratings, Historic, and Throwback collections.
- Valid specific subcollections remain intact, such as `Playoff Moments: Finals`; generic `Custom` / `Custom Cards` metadata is replaced by the visible sticker's taxonomy.
- Existing local Giannis Antetokounmpo Playoffs cards and Wilt Chamberlain Historic card were migrated to their visible promotion categories.
- Added an `Only show custom cards?` Yes/No gallery filter. It filters the gallery only while imported custom cards are enabled and is inert when the master custom-card switch is off.

## Custom Wilt Chamberlain + same-name gear inheritance - August 7, 2026

- Imported the new 1962 Wilt Chamberlain 99 OVR Pink Diamond custom card and its completed card art.
- Custom-card gear now always inherits from an identical-named NBA 2K16 player source during injection. The clean roster source is preferred, with the same-name live roster slot as a fallback.
- Card Studio package gear values are ignored and stripped during import so placeholder zero values cannot overwrite authentic player gear. If no same-name source is available, the destination slot's existing gear is preserved.
- The rule also covers existing custom cards such as the 99 OVR Giannis Antetokounmpo and future imports with a matching player name, whether or not the package includes a parent-card link. Truly new player names keep destination gear until a verified in-game gear profile is captured for them.

## Card-art and card-metadata update - August 7, 2026

- Added 24 exact card-art replacements for Dan Majerle, Cliff Robinson, Carlos Boozer, Allen Crabbe, Manu Ginobili, Jonas Valanciunas, Jalen Rose, Dwight Howard, Reggie Lewis, Otis Thorpe, Marcin Gortat, Jahlil Okafor, Eric Snow, Rolando Blackman, Tyreke Evans, Michael Finley, K.C. Jones, Chuck Person, Norman Powell, Mark Jackson, Josh Smith, Doug McDermott, Darius Miles, and Terry Cummings.
- Corrected the 2016 83 OVR Dynamic Ratings Jonas Valanciunas and 2016 80 OVR Moments Jahlil Okafor years/editions.
- Corrected the 2013 83 OVR Manu Ginobili card to Spurs Throwback Thursday.
- Corrected the 2013 82 OVR Carlos Boozer card to Chicago Bulls Historic (`Bulls Franchise 1`).
- The Chuck Person artwork visibly identifies the card as 1990 and is assigned to the 1990 81 OVR Pacers Historic entry despite the supplied filename beginning with `89`.

## Card-art additions - August 7, 2026

- Added exact card artwork for 2016 Danny Green (84 OVR Playoffs), 1997 Damon Stoudamire (84 OVR Historic), 2013 Roy Hibbert (84 OVR Pacers Throwback Thursday), 1989 Kenny Smith (84 OVR Kings Historic), and 1989 Jack Sikma (84 OVR Bucks Historic).
- Roy Hibbert artwork is assigned only to the previously corrected 2013 Pacers Throwback card (card ID `9932`).

## Reversible custom-card visibility and roster text fix - August 6, 2026

- Added a **Manage custom cards** library where individual imported cards can be hidden and restored without deleting their package or artwork.
- Custom player names are normalized to roster-safe mixed case during import and again at injection, including capitalization after hyphens and apostrophes.
- Two-digit card-year prefixes such as `'21` are kept out of NBA 2K16's first/last-name memory fields.
- Custom injection now writes NBA 2K16's normalized `CachedOverall` field explicitly, fixing invalid square glyphs in the roster-list OVR column while retaining the authored overall.

## Custom-card inheritance and deterministic injection fix — August 6, 2026

- Custom-card imports now migrate legacy negative IDs to stable positive IDs.
- Card Studio parent-card selection preserves the authored custom name/year while importing the parent's jersey number and exact linked face/portrait identity IDs.
- Custom injection now resolves its clean live template through the explicitly selected parent card.
- Fixed canonical attribute-name handling for moving midrange, standing midrange, and help-defense IQ so those values no longer vary with the overwritten destination slot.

## Custom-card taxonomy and Pink Diamond draft update — August 6, 2026

- Added a synchronized **Include custom cards** control directly to the Draft screen.
- Added Pink Diamond to the Viewer tier choices whenever custom cards are enabled and styled it as a distinct tier above Diamond.
- Pink Diamond cards now sort above Diamond cards on the main gallery regardless of OVR.
- Custom cards remain ordered highest-to-lowest by OVR and appear under their authored Viewer theme.
- Pink Diamond custom cards now share the Diamond draft pool for normal Diamond rolls and the final Diamond round.
- Card Studio 0.9.0 now supplies searchable official-player presets plus Viewer-matched Theme and Collection dropdowns.
- Custom-card import now strips an accidentally saved Card Studio search-result suffix from the player name while preserving all authored ratings and injection data.

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
