# Fix VMware Clipboard on Ubuntu 24.04 Wayland

**TL;DR:** VMware clipboard doesn't work on XWayland because `xclip` is broken. Use `xsel` instead.

```bash
sudo apt install xsel wl-clipboard

# To copy host clipboard to VMware guest:
wl-paste | xsel --clipboard --input
# Then paste in VMware guest
```

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

### Approach 2: Direct X11 Clipboard via xclip

**Test:** Set the X11 CLIPBOARD directly using `xclip`:
```bash
echo "test" | xclip -selection clipboard
```

**Result:** VMware didn't pick it up. Paste in guest did nothing.

### Approach 3: PRIMARY Selection via xclip

**Test:** Set the X11 PRIMARY selection using `xclip`:
```bash
echo "test" | xclip -selection primary
```

**Result:** VMware didn't pick it up either.

---

## The Discovery

The issue is **not** about CLIPBOARD vs PRIMARY selection. It's about **xclip vs xsel**.

We tested all combinations:

| Tool | Selection | Works? |
|------|-----------|--------|
| xclip | CLIPBOARD | No |
| xclip | PRIMARY | No |
| xsel | CLIPBOARD | **Yes** |
| xsel | PRIMARY | **Yes** |

```bash
# These do NOT work:
echo "test" | xclip -selection clipboard
echo "test" | xclip -selection primary

# These WORK:
echo "test" | xsel --clipboard --input
echo "test" | xsel --primary --input
```

---

## Root Cause

`xclip` and `xsel` handle X11 selection ownership differently under XWayland. VMware can monitor both CLIPBOARD and PRIMARY selections, but only `xsel` correctly serves the selection data to VMware under XWayland.

This is likely due to how each tool manages the selection ownership lifecycle when running on XWayland vs native X11.

---

## The Solution

Use `xsel` instead of `xclip` to sync the Wayland clipboard to X11.

### Installation

```bash
sudo apt install xsel wl-clipboard
```

### Manual Usage

```bash
# Copy from Wayland clipboard to X11 (for VMware to pick up):
wl-paste | xsel --clipboard --input

# Then paste in VMware guest — it should work
```

### Automated Solution (TODO)

A background script or service is needed to automatically sync the Wayland clipboard to X11 using `xsel` whenever the clipboard changes.

---

## Verification

```bash
# 1. Copy something to Wayland clipboard
echo "test_$(date +%s)" | wl-copy

# 2. Sync to X11 using xsel
wl-paste | xsel --clipboard --input

# 3. Verify it's set
xsel --clipboard --output

# 4. Paste in VMware guest — should work
```

---

## Summary

| What | Status |
|------|--------|
| Mutter focus restriction patch | Works, but doesn't fix VMware |
| Wayland → X11 sync | Works correctly |
| VMware + xclip | **Broken** on XWayland |
| VMware + xsel | **Works** |

The Mutter patch is unnecessary for this specific issue. The problem is that `xclip` doesn't correctly serve X11 selections to VMware under XWayland. Using `xsel` instead fixes the issue.

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
