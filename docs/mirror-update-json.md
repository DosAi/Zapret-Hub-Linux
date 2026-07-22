# Mirror update JSON (goshkow.com/zapret-hub/update)

Hotfixes may keep product version `3.0.0`. The app distinguishes builds by
**SHA256 of the portable zip** (`assets.x64.digest` / `assets.arm64.digest`), not by
`binary_updated_at`.

## Required fields

```json
{
  "product": "Zapret Hub",
  "version": "3.0.0",
  "tag": "v3.0.0",
  "assets": {
    "x64": {
      "name": "zapret_hub_3.0.0_portable_win_x64.zip",
      "download_url": "https://goshkow.com/zapret-hub/x64",
      "digest": "sha256:<hex of the exact x64 zip bytes on the mirror>",
      "size": 123456789
    },
    "arm64": {
      "name": "zapret_hub_3.0.0_portable_win_arm64.zip",
      "download_url": "https://goshkow.com/zapret-hub/arm64",
      "digest": "sha256:<hex of the exact arm64 zip bytes on the mirror>",
      "size": 123456789
    }
  }
}
```

Optional but useful: `changelog`, `github_url`, `published_at`, `assets.installer.digest`.

## Rules

1. After every hotfix re-upload of the same version, **update** `assets.x64.digest` and
   `assets.arm64.digest` to the new zip hashes (see `*.sha256` on the GitHub Release).
2. Digests must match the bytes the app downloads (installer and in-app updater verify SHA-256).
3. App update prompt:
   - remote semver **>** local → update
   - same semver and remote digest **≠** local install digest → hotfix
   - same digest → **no prompt**
4. If digests are missing from the API, same-version hotfixes cannot be detected (the app
   will not fall back to mtime / `binary_updated_at`, to avoid endless prompts).
