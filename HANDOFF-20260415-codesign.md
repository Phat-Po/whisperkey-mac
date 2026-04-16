# Handoff — Stable Code Signing (Fix TCC Permission Loss on Rebuild)

**Date**: 2026-04-15
**Project**: WhisperKey Mac
**Path**: `/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac`
**Branch**: `main`. Do NOT push without operator confirmation.

---

## The Problem

Every time `build_app.sh` runs, macOS revokes the Accessibility and Input Monitoring permissions for WhisperKey. The operator must manually delete and re-add the app in System Settings after every build.

**Root cause**: The current build signs the app with an ad-hoc identity (`codesign --sign -`). Ad-hoc signatures are ephemeral — macOS TCC tracks ad-hoc apps by their CDHash (a hash of the binary content). Each rebuild produces a new binary → new CDHash → macOS treats it as a different app → permissions revoked.

**The fix**: Replace ad-hoc signing with a named self-signed certificate (stored in Keychain). TCC then tracks the app by the certificate's stable identity instead of the file hash. Same certificate used every build = permissions persist.

No Apple Developer account or $99/year subscription needed. A locally-created self-signed certificate is sufficient for this purpose.

---

## Current Signing Setup (what to replace)

`packaging/macos/build_app.sh` line 33:
```bash
codesign --force --deep --sign - --entitlements "${ENTITLEMENTS}" "${APP_PATH}"
```

`packaging/macos/WhisperKey.spec` line 97:
```python
codesign_identity=None,
```

---

## Step-by-Step Task

### Step 1 — Check for an Existing Usable Certificate

Run:
```bash
security find-identity -v -p codesigning
```

If a certificate named something like `WhisperKey Dev` or `Apple Development: ...` already appears with a valid hash, use that name and **skip Step 2**.

### Step 2 — Create a Self-Signed Code Signing Certificate (one-time, operator action)

This step requires the operator to do it manually in the GUI:

1. Open **Keychain Access** (Spotlight → Keychain Access)
2. Menu bar: **Keychain Access → Certificate Assistant → Create a Certificate...**
3. Fill in:
   - **Name**: `WhisperKey Dev` (use this exact name — it goes into the build script)
   - **Identity Type**: Self Signed Root
   - **Certificate Type**: Code Signing
   - Leave all other fields at defaults
4. Click **Create**, then **Done**
5. Verify it appeared: `security find-identity -v -p codesigning` — you should see `WhisperKey Dev`

### Step 3 — Update `build_app.sh`

File: `packaging/macos/build_app.sh`

Change line 33 from:
```bash
codesign --force --deep --sign - --entitlements "${ENTITLEMENTS}" "${APP_PATH}"
```
To:
```bash
codesign --force --deep --sign "WhisperKey Dev" --entitlements "${ENTITLEMENTS}" "${APP_PATH}"
```

### Step 4 — Update `WhisperKey.spec`

File: `packaging/macos/WhisperKey.spec`

Change line 97 from:
```python
codesign_identity=None,
```
To:
```python
codesign_identity="WhisperKey Dev",
```

Also change line 98 from:
```python
entitlements_file=None,
```
To:
```python
entitlements_file=str(project_root / "packaging" / "macos" / "entitlements.plist"),
```

(The entitlements file already exists and is correct — this just ensures PyInstaller passes it during its own signing step before `build_app.sh` does the final sign.)

### Step 5 — Rebuild and Verify

```bash
cd "/Volumes/轻松打爆你/VIBE CODING/10_PROJECTS_ACTIVE/20260302__python__vibemouse-mac"
packaging/macos/build_app.sh
```

After build, inspect the signing identity:
```bash
codesign -dv --verbose=4 dist/WhisperKey.app 2>&1 | grep -E "Authority|TeamIdentifier|Identifier|designated"
```

**Expected output** should show:
- `Authority=WhisperKey Dev` (or similar cert name)
- `Identifier=com.phatpo.whisperkey`
- The designated requirement should be cert-based (contains `certificate`), NOT hash-based (should NOT contain `cdhash`)

If it shows `Signature=adhoc`, the signing step didn't use the certificate — recheck that `"WhisperKey Dev"` matches exactly what `security find-identity` returned.

### Step 6 — Grant TCC Once

After this first build with the new cert:
1. System Settings → Privacy & Security → **Accessibility** → remove old WhisperKey if present → `+` → add `dist/WhisperKey.app`
2. System Settings → Privacy & Security → **Input Monitoring** → same

### Step 7 — Prove It's Fixed (Critical Test)

Rebuild the app a second time without touching System Settings:
```bash
packaging/macos/build_app.sh
```

Then test the hotkey works **without re-granting permissions**. If hold-to-record works, the fix is confirmed.

### Step 8 — Commit

```bash
git add packaging/macos/build_app.sh packaging/macos/WhisperKey.spec
git commit -m "fix: stable code signing to preserve TCC permissions across rebuilds"
```

---

## If the Self-Signed Cert Doesn't Stabilize TCC

Some macOS versions are stricter and still invalidate TCC for self-signed certs if the binary content changes. In that case, the next level of fix is a free Apple Developer account:

1. Sign up at developer.apple.com (free)
2. In Xcode → Settings → Accounts → add Apple ID → Manage Certificates → Create "Mac Development" cert
3. `security find-identity -v -p codesigning` will now show a cert with a real Team ID
4. Use that identity (the full string, e.g. `"Apple Development: your@email.com (TEAMID)"`), or just the Team ID

With a real Team ID, TCC tracks by `Team ID + bundle ID` = guaranteed stable.

---

## Key Files

| File | What to edit |
|------|-------------|
| `packaging/macos/build_app.sh` | Line 33: `--sign -` → `--sign "WhisperKey Dev"` |
| `packaging/macos/WhisperKey.spec` | Line 97–98: `codesign_identity` and `entitlements_file` |
| `packaging/macos/entitlements.plist` | No changes needed — current entitlements are correct |

---

## Project State at Handoff

- Latest commit: `67bd12d feat: gpt-5.4 models, usage monitoring tab, ASR plain text output`
- Tests: 110 passed (`venv/bin/python -m pytest -q`)
- App builds and runs correctly with ad-hoc signing
- Bundle ID: `com.phatpo.whisperkey`

## Constraints

- Do NOT `git push` without operator confirmation
- Do NOT edit `.env*` files
- Do NOT touch `~/Library/LaunchAgents/com.whisperkey.plist`
- Use project venv: `.venv/bin/python`, not system `python3`
- Run `packaging/macos/build_app.sh` for all builds (don't call PyInstaller directly)
