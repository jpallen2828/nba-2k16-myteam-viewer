# Public Release Checklist

- [ ] Test the viewer and one controlled injection on a fresh legal install.
- [ ] Save the generated `nba2k16-myteam-compatibility-report.json` from that machine.
- [ ] Do not ship any game executable, game DLL, archive container, extracted game asset, or roster save.
- [ ] Keep `source/viewer/data/card-images/` out of the GitHub repository until its third-party rights review is complete.
- [ ] Review card metadata, player photos, team/NBA marks, and archived source material with legal counsel before publishing a release asset that includes them.
- [ ] Add dependency notices and pin the tested Python/build versions.
- [ ] Create the GitHub repository from this folder, verify `git status` has no game files, then choose the intended repository visibility and release license.
