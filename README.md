# Fix VMware Clipboard on Ubuntu 24.04 Wayland

**TL;DR:** VMware Workstation on Linux/Wayland monitors the **PRIMARY** selection (middle-click paste), not **CLIPBOARD** (Ctrl+C/V). Install `autocutsel` to sync them.

```bash
sudo apt install autocutsel
autocutsel -fork -selection CLIPBOARD
```

Add `autocutsel -fork -selection CLIPBOARD` to your startup applications to make it permanent.

---

## The Problem

Copy/paste between VMware Workstation Pro guest and Ubuntu 24.04 host (Wayland) doesn't work, even though:
- VMware Tools is installed and running in the guest
- The same VM works perfectly when the host is Windows 11
- Clipboard is enabled in VM settings

Tested with:
- Ubuntu 24.04 LTS (Noble) with GNOME on Wayland
- Mutter 46.2
- VMware Workstation 17 Pro 17.6.4 (build-24832109)

---

## What We Tried (And Why It Didn't Work)

### Approach 1: Patching Mutter to Remove Focus Restrictions

**Hypothesis:** Wayland's Mutter compositor restricts clipboard access to only the focused window. Since VMware runs under XWayland, it might not receive clipboard updates when unfocused.

**What we did:** Patched `meta-wayland-data-device.c` and `meta-wayland-data-device-primary.c` to:
1. Remove focus checks in `data_device_set_selection()` and `primary_device_set_selection()`
2. Notify ALL Wayland clients of clipboard changes (not just the focused one)

**Result:** The patch worked correctly for Wayland→X11 sync, but **VMware clipboard still didn't work**.

**How we verified the patch worked:**
```bash
# Install test tools
sudo apt install xclip wl-clipboard

# Copy via Wayland
echo "test_$(date +%s)" | wl-copy

# Check if X11 sees it
xclip -selection clipboard -o
```

Both commands showed the same content, proving Wayland→X11 CLIPBOARD sync works.

### Approach 2: Direct X11 Clipboard Test

**Test:** Set the X11 CLIPBOARD directly (bypassing Wayland entirely):
```bash
echo "direct_x11_test" | xclip -selection clipboard
```

**Result:** VMware still didn't pick it up. Paste in guest did nothing.

**Conclusion:** The issue is NOT with Wayland/XWayland clipboard sync. VMware itself isn't monitoring CLIPBOARD.

---

## The Discovery

We tested the **PRIMARY** selection (the X11 "highlight to copy, middle-click to paste" mechanism):

```bash
echo "primary_test" | xclip -selection primary
```

**Result:** IT WORKED! The text appeared when pasting in the VMware guest.

---

## Root Cause

VMware Workstation on Linux monitors the **PRIMARY** selection, not the **CLIPBOARD** selection, when running under XWayland.

| Selection | Mechanism | What VMware Does |
|-----------|-----------|------------------|
| CLIPBOARD | Ctrl+C / Ctrl+V | **Ignored** by VMware on XWayland |
| PRIMARY | Highlight text / Middle-click | **Monitored** by VMware |

This is likely a bug or limitation in VMware's Linux clipboard implementation when running under XWayland (vs native X11).

---

## The Solution

Use `autocutsel` to automatically synchronize CLIPBOARD and PRIMARY selections:

### Installation

```bash
sudo apt install autocutsel
```

### Usage

```bash
# Run in background (syncs CLIPBOARD → PRIMARY)
autocutsel -fork -selection CLIPBOARD
```

### Make It Permanent

Add to GNOME startup applications:

1. Open "Startup Applications" (search in Activities)
2. Click "Add"
3. Name: `Autocutsel`
4. Command: `autocutsel -fork -selection CLIPBOARD`
5. Save

Or create a desktop file:

```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/autocutsel.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Autocutsel
Exec=autocutsel -fork -selection CLIPBOARD
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
```

---

## Verification

After starting autocutsel:

1. Copy text in a Wayland app on the host (Ctrl+C)
2. Click into VMware guest
3. Paste (Ctrl+V) — should work now

To verify the sync is working:
```bash
# Copy something
echo "clipboard_test" | wl-copy

# Check both selections
echo "CLIPBOARD:" && xclip -selection clipboard -o
echo "PRIMARY:" && xclip -selection primary -o
```

Both should show the same content.

---

## Summary

| What | Status |
|------|--------|
| Mutter focus restriction patch | Works, but doesn't fix VMware |
| Wayland → X11 CLIPBOARD sync | Works correctly |
| VMware monitoring CLIPBOARD | **Broken** on XWayland |
| VMware monitoring PRIMARY | Works |
| autocutsel CLIPBOARD↔PRIMARY sync | **Fixes the issue** |

The Mutter patch is unnecessary for this specific issue. The problem is entirely on VMware's side — it monitors the wrong X11 selection when running under XWayland.

---

## Why Not Patch Mutter Instead?

We considered patching Mutter to auto-sync CLIPBOARD→PRIMARY, but:

1. **Complexity:** Requires adding sync logic, not just removing checks
2. **Risk:** Could cause infinite loops or break PRIMARY semantics
3. **Maintenance:** Harder to maintain across Mutter versions
4. **autocutsel exists:** Purpose-built, 66KB, battle-tested solution

---

## Related Issues

- [VMware open-vm-tools #510](https://github.com/vmware/open-vm-tools/issues/510)
- [VMware open-vm-tools #443](https://github.com/vmware/open-vm-tools/issues/443)

---

## Environment Details

Tested configuration:
```bash
lsb_release -ds              # Ubuntu 24.04.* LTS
echo $XDG_SESSION_TYPE       # wayland
gnome-shell --version        # GNOME Shell 46.*
vmware --version             # VMware Workstation 17.6.4 build-24832109
```

---

## License

Public Domain (Unlicense). See [LICENSE](LICENSE).
