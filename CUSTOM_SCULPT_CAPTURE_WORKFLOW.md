# Custom-Sculpted Player Capture and Injection

Use this workflow for any NBA 2K16 Create-A-Player whose exact sculpt must survive MyTEAM Viewer injection.

## Capture authority

1. Back up and identify the exact loaded roster before any experiment.
2. Resolve the canonical player from the current live team-data pointers. Never trust a slot saved from an earlier process.
3. Confirm the correct player visually in Roster Creator and Create A Player.
4. Make one controlled sculpt change in the private Create-A-Player editor buffer and compare it with the untouched baseline.

For the supported NBA2K16.exe build, the verified linked data is:

- Player row `+0x78` points to a 52-byte facial sculpt DNA block.
- Player row `+0x80` points to a 132-byte CAP appearance/body block.

Capture the bytes, not either pointer. Pointers are process-local and must never be stored in a card or copied to a destination row.

## Custom-card fields

Store verified captures under `card.customPlayerData`:

```json
{
  "sculptDnaHex": "...exactly 52 bytes as hexadecimal...",
  "sculptDnaSha256": "...",
  "sculptDnaSize": 52,
  "sculptPointerRowOffset": "0x78",
  "sculptCaptureVerified": true,
  "appearanceBlockHex": "...exactly 132 bytes as hexadecimal...",
  "appearanceBlockSha256": "...",
  "appearanceBlockSize": 132,
  "appearancePointerRowOffset": "0x80",
  "appearanceBlockCaptureVerified": true
}
```

The injector validates both lengths and fails closed on malformed hexadecimal or a missing destination pointer.

## Injection order and ownership

1. Build the destination player row from its existing shell so its live pointers remain destination-owned.
2. Apply normal card metadata, identity, ratings, tendencies, badges, signatures, gear, height, and other supported fields.
3. Follow the destination row's `+0x80` pointer and write the complete verified 132-byte appearance block. This full capture is authoritative over generic appearance defaults.
4. Follow the destination row's `+0x78` pointer and write the verified 52-byte sculpt DNA.
5. Apply the same linked writes to validated cache/editor copies when the normal injection path refreshes those rows.
6. Include every linked write in rollback tracking.

Never copy the source row's `+0x78` or `+0x80` pointer values, and never replay an entire row captured in another NBA2K16.exe process.

## Required validation

For each newly captured custom sculpt:

1. Unit-test the exact card bytes and required sizes.
2. Inject onto a reversible visible destination.
3. Verify both destination blocks byte-for-byte against the stored card data.
4. Verify destination and source pointers are different.
5. Verify card metadata and artwork did not change unexpectedly.
6. Confirm the model visually in-game.
7. Restart NBA 2K16, reload the roster, inject again, and confirm the result.
8. Repeat on a different destination row.
9. Prove source independence by injecting from the stored card capture without relying on the original source row's linked buffers.

The Luka Doncic card `1761984123/custom-luka-doncic-2026-1761984123` is the first confirmed reference implementation of this workflow.
