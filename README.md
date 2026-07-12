# NBA 2K16 MyTEAM Viewer

An unofficial, non-commercial companion app for browsing archived NBA 2K16 MyTEAM cards and injecting selected cards into a roster loaded in a local copy of NBA 2K16.

## Requirements

- A legally obtained Windows copy of NBA 2K16.
- Windows 10 or newer.
- NBA 2K16 must be running with the intended roster loaded before using roster injection.
- Patch 0 and other executable builds can be used if the app can read the expected live roster structure.
- This project does not include, install, replace, or download NBA 2K16 executables, DLLs, archive containers, roster saves, or other game files.

## Using the App

1. Download the application package [here](https://github.com/jpallen2828/nba-2k16-myteam-viewer/releases) and extract the ZIP to local storage.
2. Start NBA 2K16 and load the roster you want to edit.
3. Start `NBA 2K16 MyTEAM Viewer.exe`.
4. Browse, draft, or create a lineup in the viewer.
5. Open the roster injector, choose the correct roster file, and select the team to overwrite.
6. If the app cannot automatically verify the loaded roster, only use the manual confirmation button when that exact roster is already open in NBA 2K16.
7. On the first injection for a newly detected NBA 2K16 executable build, the viewer may take a short moment to create a local compatibility profile. Later injections with that same build use the saved profile and should be much faster.
8. In NBA 2K16, rebuild the rotations for the team you overwrote, then save the roster. This is recommended for the best in-game experience.

If the app cannot detect the installation or roster folder, run `Diagnose NBA 2K16 Install.exe` and include the generated compatibility report when asking for support.

Because this is an unsigned fan-made tool, Windows Defender or SmartScreen may warn about it or block it even when downloaded from the official project release. Users who trust the release and have reviewed the source code may need to allow or whitelist `NBA 2K16 MyTEAM Viewer.exe` in Windows Security for the app to run normally.

## Acknowledgments

Special thanks to my friend Ray for helping to fix some of the tendencies, gear, hot zones, and more of many of these players. This project would not be as good without him.

## Build from source

The prebuilt ZIP is the recommended option for most users. To build the application yourself, use Windows with Python 3.13 or newer and run these commands from the repository's top-level folder:

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 source\build_public_release.py
```

The source repository may exclude large generated caches or release-only assets. Build outputs are created under `build/`, `dist/`, and `release/`.

## Disclaimer

This is an independent fan project. It is not affiliated with, endorsed by, or sponsored by 2K, Take-Two, the NBA, the NBPA, or any rights holder. See [GAME_FILES_NOT_INCLUDED.md](GAME_FILES_NOT_INCLUDED.md) and [THIRD_PARTY_AND_RIGHTS.md](THIRD_PARTY_AND_RIGHTS.md) for more detail.
