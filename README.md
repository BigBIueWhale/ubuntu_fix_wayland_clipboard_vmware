# Fix VMware Clipboard on Ubuntu 24.04 Wayland

**TL;DR:** VMware clipboard doesn't work on XWayland because of how XWayland serves clipboard data. Using `xsel` as a bridge works, but causes UI flickering. No clean solution exists yet.

```bash
sudo apt install xsel wl-clipboard

# Manual sync (run each time you want to copy to VMware):
wl-paste | xsel --clipboard --input
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

## How xsel Works (And Why It Causes UI Flickering)

When you run `xsel --clipboard --input`, it:

1. **Creates a 1x1 pixel X11 window** to claim clipboard ownership
2. Stores the clipboard data
3. Waits for other applications to request the data
4. Serves the data when requested

You can see these windows:
```bash
xwininfo -root -tree | grep xsel
# Output:
#   0x3000001 "xsel": ("xsel" "XSel")  1x1+0+0  +0+0
```

**The problem:** Even though the window is 1x1 pixels, GNOME's Mutter compositor still:
- Registers it as a new window
- Shows it briefly in the dock/taskbar
- Causes the trash can icon to "bounce"
- Creates visible UI flickering

Every time we sync the clipboard, a new xsel window is created, causing this flickering.

### Attempted Workarounds (None Fully Successful)

**1. Using `xdotool windowunmap` to hide xsel windows:**
```bash
printf "%s" "$CONTENT" | xsel --clipboard --input &
sleep 0.05
for wid in $(xdotool search --name "xsel"); do
    xdotool windowunmap "$wid"
done
```
**Result:** Creates multiple xsel processes, doesn't eliminate flickering.

**2. Using `--nodetach` flag:**
```bash
xsel --clipboard --input --nodetach
```
**Result:** Doesn't help with the window creation issue.

**3. Persistent xsel process:**
Attempting to keep a single xsel process running and feed it new data doesn't work because xsel reads input once and then holds it.

---

## The Solution (Works But Has Issues)

### Installation

```bash
sudo apt install xsel wl-clipboard
```

### Manual Usage

For occasional use, manually sync when needed:
```bash
# Copy something with Ctrl+C, then run:
wl-paste | xsel --clipboard --input

# Then paste in VMware guest
```

### Automated Daemon (Causes UI Flickering)

This polling daemon works but causes UI flickering every time the clipboard changes:

```bash
#!/bin/bash
# Save as: ~/.local/bin/clipboard-sync-vmware.sh

echo "Clipboard sync daemon for VMware"
echo "Press Ctrl+C to stop"

LAST_HASH=""
while true; do
    CURRENT=$(wl-paste 2>/dev/null)
    CURRENT_HASH=$(echo "$CURRENT" | md5sum | cut -d" " -f1)
    if [ "$CURRENT_HASH" != "$LAST_HASH" ] && [ -n "$CURRENT" ]; then
        printf "%s" "$CURRENT" | xsel --clipboard --input
        echo "[$(date +%H:%M:%S)] Synced: ${CURRENT:0:40}..."
        LAST_HASH="$CURRENT_HASH"
    fi
    sleep 1
done
```

**Known issues with this daemon:**
- UI flickers every time clipboard is synced
- Trash can icon bounces in GNOME dock
- Desktop may feel less responsive
- Creates new xsel process on every sync

### Why `wl-paste --watch` Doesn't Work

The ideal solution would be:
```bash
wl-paste --watch sh -c 'xsel --clipboard --input'
```

But this fails on GNOME with:
```
Watch mode requires a compositor that supports the wlroots data-control protocol
```

GNOME's Mutter compositor doesn't support this protocol (it's wlroots-specific).

---

## Summary

| What | Status |
|------|--------|
| Mutter focus restriction patch | Works, but doesn't fix VMware |
| Wayland → X11 sync via XWayland | Broken for VMware |
| VMware + xclip | **Broken** on XWayland |
| VMware + xsel | **Works** but causes UI flickering |
| `wl-paste --watch` | Not supported on GNOME/Mutter |
| Clean automated solution | **Does not exist yet** |

The fundamental issue is that `xsel` must create an X11 window to claim clipboard ownership, and GNOME/Mutter treats this as a regular window, causing UI flickering.

---

## What Would Fix This Properly

1. **VMware fix:** VMware could update their Linux clipboard code to work properly with XWayland's clipboard serving mechanism (like xclip does... but in a way that works)

2. **GNOME/Mutter fix:** Support the wlroots data-control protocol so `wl-paste --watch` works

3. **xsel fix:** Option to create the ownership window as "override-redirect" so window managers ignore it

4. **XWayland fix:** Fix whatever difference exists between how XWayland serves clipboard data vs how xsel does it

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
