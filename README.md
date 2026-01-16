# Fix VMware/VirtualBox Clipboard on Ubuntu 24.04 Wayland (Mutter 46.2)

How to fix broken clipboard integration between VMware/VirtualBox guests and Ubuntu 24.04 hosts running Wayland?

This README is **strict and opinionated**. Follow it **exactly** on **Ubuntu 24.04 LTS (Noble)** with **GNOME on Wayland** and **Mutter 46.2**.

Tested with VMware Workstation 17 Pro 17.6.4 (build-24832109).

> **What this does:** Applies a minimal patch to GNOME's Mutter compositor to remove
> the focus-based clipboard restrictions that break VM clipboard integration.
>
> **Why it works:** X11 allowed unrestricted clipboard access for 30+ years. It worked fine.
> Wayland added focus restrictions that break VMware, VirtualBox, clipboard managers,
> and any app that needs background clipboard access. This patch removes those restrictions.
>
> Use only on machines you own/administer. This intentionally bypasses a Wayland "security" feature.

---

## Problem Description

### Symptoms
- Copy/paste between VMware/VirtualBox guest and Wayland host fails intermittently
- Clipboard works only when VM window is actively focused
- Copying in a Wayland app and pasting in VM guest fails if you click into VM after copying
- Copying in VM guest fails to appear in Wayland apps

### Root Cause
Wayland's Mutter compositor restricts clipboard access to only the **currently focused window**.
This is a policy decision, not a technical requirement.

VMware and VirtualBox are X11 applications. On a Wayland desktop, they run under **XWayland** —
a compatibility layer that provides an X11 server for legacy apps while acting as a Wayland
client to the compositor.

The focus restrictions in Mutter's Wayland clipboard code prevent unfocused Wayland clients from:
1. Writing to the clipboard
2. Receiving clipboard change notifications

Since XWayland is "just another Wayland client" from Mutter's perspective, these restrictions
block clipboard operations when VMware doesn't have focus.

### The Solution
Remove the focus checks entirely. If X11 could handle unrestricted clipboard access for
30+ years, so can Wayland.

---

## Quick Start (TL;DR)

```bash
# 1) Clone this repo
git clone https://github.com/BigBIueWhale/ubuntu_fix_wayland_clipboard_vmware.git
cd ubuntu_fix_wayland_clipboard_vmware
```

**Expect:** A new folder with the patcher script.

```bash
# 2) Enable source repositories and install build dependencies
sudo apt update
sudo apt install -y git build-essential ninja-build meson pkg-config

# Enable deb-src (required for apt build-dep)
sudo cp /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources.bak
sudo sed -i 's/^\(Types:\s*deb\)\(\s\+\|\s*$\)/\1 deb-src\2/' /etc/apt/sources.list.d/ubuntu.sources
sudo apt update
sudo apt build-dep -y mutter
```

**Expect:** Packages install successfully. If `build-dep` fails with "deb-src" error, check Section 1.

```bash
# 3) Clone mutter and checkout the exact version
mkdir -p ./sources
git clone https://gitlab.gnome.org/GNOME/mutter.git ./sources/mutter
cd ./sources/mutter && git checkout 46.2 && cd ../..
```

**Expect:** Mutter 46.2 source tree in `./sources/mutter`.

```bash
# 4) Apply the patch
python3 ./patch_mutter_clipboard.py ./sources/mutter
```

**Expect:**
- Validates source layout using strict sentinels
- Creates `.bak` backups of patched files
- Prints `[OK] Patched ...` for each file
- Shows diff preview of changes

```bash
# 5) Build mutter
cd ./sources/mutter
meson setup build --prefix=/usr --buildtype=release
ninja -C build
cd ../..
```

**Expect:** Meson configures and Ninja compiles without errors.

```bash
# 6) Install and restart GNOME Shell
sudo ninja -C ./sources/mutter/build install
# Then: Log out and log back in (or reboot)
```

**Expect:** After logging back in, clipboard works between VM and host.

```bash
# 7) Prevent apt from overwriting your patch
sudo apt-mark hold mutter mutter-common libmutter-14-0
```

**Expect:** `mutter` shows in `apt-mark showhold`.

---

## 0) Preconditions — Verify Environment

```bash
lsb_release -ds
```

**Expect:** `Ubuntu 24.04.* LTS`

```bash
dpkg -s mutter-common | grep '^Version'
```

**Expect:** `46.2-1ubuntu0.24.04.*` — This patcher targets **46.2** specifically.

```bash
echo $XDG_SESSION_TYPE
```

**Expect:** `wayland` — If you see `x11`, you're not on Wayland and don't need this patch.

```bash
gnome-shell --version
```

**Expect:** `GNOME Shell 46.*`

---

## 1) Install Build Dependencies

```bash
sudo apt update
sudo apt install -y git build-essential ninja-build meson pkg-config
```

**Expect:** Packages install successfully.

### Enable Source Repositories (required for `apt build-dep`)

Ubuntu 24.04 uses Deb822 format. We need to enable source repos:

```bash
# Backup first
sudo cp /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources.bak
```

**Expect:** Silent success.

```bash
# Add deb-src to Types: deb lines
sudo sed -i 's/^\(Types:\s*deb\)\(\s\+\|\s*$\)/\1 deb-src\2/' /etc/apt/sources.list.d/ubuntu.sources
```

**Expect:** No output. File now has `Types: deb deb-src`.

```bash
# Refresh and install build deps
sudo apt update
sudo apt build-dep -y mutter
```

**Expect:** Build dependencies install. If you see "You must put some 'deb-src' URIs...", the sed command didn't work — check `/etc/apt/sources.list.d/ubuntu.sources` manually.

---

## 2) Clone Mutter Source (Project-Local)

```bash
mkdir -p ./sources
git clone https://gitlab.gnome.org/GNOME/mutter.git ./sources/mutter
cd ./sources/mutter && git checkout 46.2
```

**Expect:** `HEAD is now at ... Bump version to 46.2`

Verify:
```bash
git describe --tags --exact-match
```

**Expect:** `46.2`

```bash
cd ../..
```

Your project tree should look like:
```
ubuntu_fix_wayland_clipboard_vmware/
├── patch_mutter_clipboard.py
├── README.md
└── sources/
    └── mutter/   # checked out at tag 46.2
```

---

## 3) Apply the Patch

```bash
python3 ./patch_mutter_clipboard.py ./sources/mutter
```

**Expect:**
- `[info] Detected version: 46.2`
- `[OK] Source tree validated against mutter 46.2 layout`
- `[OK] Patched .../meta-wayland-data-device.c`
- `[OK] Patched .../meta-wayland-data-device-primary.c`
- Diff preview showing the removed focus checks

If you see `[ERROR]` about sentinels, your mutter version doesn't match 46.2.
See **Troubleshooting** below.

---

## 4) Build Mutter

```bash
cd ./sources/mutter
meson setup build --prefix=/usr --buildtype=release
ninja -C build
```

**Expect:** Compilation completes without errors.

If meson fails with missing dependencies:
```bash
sudo apt build-dep mutter
meson setup build --wipe --prefix=/usr --buildtype=release
ninja -C build
```

---

## 5) Install and Restart

```bash
sudo ninja -C build install
```

**Expect:** Files installed to `/usr`.

**Then restart GNOME Shell:**
- **Option A (recommended):** Log out and log back in
- **Option B:** Reboot
- **Option C (X11 only):** `killall -3 gnome-shell`

---

## 6) Prevent APT from Overwriting Your Patch

```bash
sudo apt-mark hold mutter mutter-common libmutter-14-0
```

**Verify:**
```bash
apt-mark showhold | grep mutter
```

**Expect:** `mutter`, `mutter-common`, `libmutter-14-0` listed.

> **Trade-off:** While held, you won't receive mutter security updates.
> When ready to update: unhold, upgrade, re-apply patch, hold again.

---

## 7) Testing

1. Start your VM (VMware or VirtualBox) with guest tools installed
2. Copy text in a Wayland app on the host
3. Click into the VM and paste — should work
4. Copy text in the VM
5. Click to a Wayland app and paste — should work

The clipboard should now work regardless of which window is focused.

---

## What Exactly Changes (Code-Level)

### File: `src/wayland/meta-wayland-data-device.c`

**Patch 1: Remove focus check in `data_device_set_selection()`**
- [Lines 1064-1070](https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device.c#L1064-1070)
- Removes the check that cancels clipboard writes from unfocused apps
- Any Wayland client can now set the clipboard, regardless of focus

**Patch 2: Notify ALL clients in `owner_changed_cb()`**
- [Lines 1107-1127](https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device.c#L1107-1127)
- Removes the focus check that blocked notifications to unfocused apps
- **Critical fix:** Iterates BOTH `resource_list` AND `focus_resource_list`

  Mutter splits client resources into two lists:
  - `resource_list` — unfocused clients
  - `focus_resource_list` — the currently focused client

  Original code only notified `focus_resource_list`. Our patch notifies both lists,
  ensuring ALL clients (including XWayland) receive clipboard updates.

### File: `src/wayland/meta-wayland-data-device-primary.c`

Same pattern for PRIMARY selection (middle-click paste):

**Patch 1:** [Lines 184-190](https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device-primary.c#L184-190)
- Remove focus check in `primary_device_set_selection()`

**Patch 2:** [Lines 212-233](https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device-primary.c#L212-233)
- Notify ALL clients in `owner_changed_cb()` (iterate both lists)

### All Focus-Related Code Paths (Complete Audit)

Mutter 46.2 has **6 locations** that reference `meta_wayland_seat_get_input_focus_client()`:

| Location | Function | Patched? | Why? |
|----------|----------|----------|------|
| data-device.c:1065 | `data_device_set_selection()` | **YES** | Restricts who can write CLIPBOARD |
| data-device.c:1109 | `owner_changed_cb()` | **YES** | Restricts who gets CLIPBOARD notifications |
| data-device.c:1258 | `sync_focus()` | No | Bookkeeping only (see below) |
| data-device-primary.c:185 | `primary_device_set_selection()` | **YES** | Restricts who can write PRIMARY |
| data-device-primary.c:214 | `owner_changed_cb()` | **YES** | Restricts who gets PRIMARY notifications |
| data-device-primary.c:357 | `sync_focus()` | No | Bookkeeping only (see below) |

**Why `sync_focus()` doesn't need patching:**

The `meta_wayland_data_device_sync_focus()` and `meta_wayland_data_device_primary_sync_focus()`
functions are called when focus *changes*. They:
1. Move client resources between `resource_list` and `focus_resource_list`
2. Send the current clipboard state to the newly focused client

These functions are **not restrictions** — they're additive. They ensure a client knows what's
on the clipboard when it gains focus. This is necessary functionality that our patches don't
interfere with. The restrictions we remove are:
- Rejecting clipboard *writes* from unfocused clients
- Blocking clipboard *notifications* to unfocused clients

---

## How VMware/VirtualBox Clipboard Works on Wayland

Understanding why this patch works requires understanding the XWayland architecture:

### The XWayland Bridge

```
┌─────────────────────────────────────────────────────────────────┐
│                        WAYLAND SESSION                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐     ┌──────────────────────────────────────┐  │
│  │   Native     │     │            XWayland Process          │  │
│  │  Wayland App │     │  ┌────────────┐  ┌────────────────┐  │  │
│  │  (Firefox,   │     │  │ X11 Server │  │ Wayland Client │  │  │
│  │   Nautilus)  │     │  │  (for X11  │  │  (to Mutter)   │  │  │
│  └──────┬───────┘     │  │   apps)    │  └───────┬────────┘  │  │
│         │             │  └─────┬──────┘          │           │  │
│         │             │        │                 │           │  │
│         │             │  ┌─────┴──────┐          │           │  │
│         │             │  │  VMware /  │          │           │  │
│         │             │  │ VirtualBox │          │           │  │
│         │             │  │  (X11 app) │          │           │  │
│         │             │  └────────────┘          │           │  │
│         │             └──────────────────────────┼───────────┘  │
│         │                                        │              │
│         └──────────────────┬─────────────────────┘              │
│                            │                                    │
│                            ▼                                    │
│              ┌─────────────────────────────┐                    │
│              │     Mutter (Compositor)     │                    │
│              │  meta-wayland-data-device.c │ ◄── THIS IS WHERE  │
│              │     wl_data_device API      │     THE PATCH GOES │
│              └─────────────────────────────┘                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Clipboard Flow: Guest → Host

1. You copy text in the **VM guest** OS
2. **VMware Tools / VBox Guest Additions** send clipboard data to host process
3. **VMware/VBox host process** (an X11 app) calls `XSetSelectionOwner()` to claim X11 clipboard
4. **XWayland** (as X11 server) receives this, then (as Wayland client) calls `wl_data_device.set_selection`
5. **Mutter** receives this in `data_device_set_selection()`
6. ❌ **Without patch:** If a native Wayland app has focus, XWayland is not the "focused client" → REJECTED
7. ✅ **With patch:** Focus check removed → clipboard is set successfully

### Clipboard Flow: Host → Guest

1. You copy text in a **native Wayland app**
2. **Mutter** updates the clipboard owner
3. `owner_changed_cb()` is called to notify clients
4. ❌ **Without patch:** Only the focused client is notified; XWayland may not receive the update
5. ✅ **With patch:** ALL clients notified, including XWayland
6. **XWayland** syncs to X11 clipboard
7. **VMware/VBox** can now read the clipboard and send to guest

### When Focus Changes

Mutter also has `meta_wayland_data_device_sync_focus()` which sends the current clipboard
state to a client when it gains focus. This means some clipboard operations work even
without the patch — but only after you click into the target window. The patch enables:

- **Background clipboard sync:** VMware Tools pushing clipboard updates without requiring focus
- **Immediate availability:** Clipboard ready instantly, not just after focus change
- **Bidirectional reliability:** Both copy and paste directions work consistently

---

## Rollback (Return to Stock)

**Option A — Reinstall distro packages:**
```bash
sudo apt-mark unhold mutter mutter-common libmutter-14-0
sudo apt install --reinstall mutter mutter-common libmutter-14-0
# Log out and back in
```

**Option B — Restore from backups and rebuild:**
```bash
cd ./sources/mutter
cp src/wayland/meta-wayland-data-device.c.bak src/wayland/meta-wayland-data-device.c
cp src/wayland/meta-wayland-data-device-primary.c.bak src/wayland/meta-wayland-data-device-primary.c
meson setup build --wipe --prefix=/usr --buildtype=release
ninja -C build
sudo ninja -C build install
# Log out and back in
```

**Reverting the Deb822 source repos change (optional):**
```bash
sudo mv /etc/apt/sources.list.d/ubuntu.sources.bak /etc/apt/sources.list.d/ubuntu.sources
sudo apt update
```

**Expect:** Source indices no longer fetched; APT configuration returns to default.

---

## Troubleshooting

### "Sentinel not found" error
Your mutter version doesn't match 46.2. Check:
```bash
dpkg -s mutter-common | grep Version
```

If your version differs significantly, you'll need to adapt the patch manually
by comparing the upstream code at your version's tag.

### Build fails with missing dependencies
```bash
sudo apt build-dep mutter
meson setup build --wipe --prefix=/usr --buildtype=release
```

### "Backup already exists" error
The patcher refuses to overwrite existing backups. Move them first:
```bash
mv ./sources/mutter/src/wayland/*.bak /tmp/
```

### Clipboard still doesn't work

1. Verify you're on Wayland:
   ```bash
   echo $XDG_SESSION_TYPE
   ```
   **Expect:** `wayland`

2. Check VM guest tools are installed and running:
   - **VMware:** `systemctl status vmtoolsd` or check VMware menu → "Install VMware Tools"
   - **VirtualBox:** `systemctl status vboxadd-service` or Devices → "Insert Guest Additions CD"

3. Watch clipboard-related logs in real-time:
   ```bash
   journalctl --user -f | grep -i -E 'clipboard|selection|data.device'
   ```

4. Check if XWayland is running (required for VMware/VBox):
   ```bash
   pgrep -a Xwayland
   ```
   **Expect:** A running Xwayland process

5. Verify patched mutter is loaded (not stock):
   ```bash
   strings /usr/lib/x86_64-linux-gnu/libmutter-14.so.0 | grep VMWARE_CLIPBOARD_PATCH
   ```
   **Expect:** Output containing `VMWARE_CLIPBOARD_PATCH` (our marker)

### GNOME Shell crashes after install
Reinstall stock mutter:
```bash
sudo apt install --reinstall mutter mutter-common libmutter-14-0
```

---

## Why This Is The Right Approach

1. **X11 Precedent:** X11 allowed unrestricted clipboard access for 30+ years. It worked.
   No security apocalypse occurred.

2. **What Wayland Broke:**
   - VMware clipboard integration (X11 app running under XWayland)
   - VirtualBox clipboard integration (same reason)
   - Clipboard managers (GPaste, CopyQ, etc.)
   - Remote desktop software
   - Automation tools
   - Any app that needs to read/write clipboard without having focus

3. **The "Security" Argument:** Marginal at best. A malicious app could still grab
   clipboard when it gets focus. The restriction mainly breaks legitimate use cases.

4. **GNOME's Alternative:** GNOME could implement `ext-data-control-v1` to allow
   "privileged" clipboard access, but they haven't. Even if they did, it would
   require all affected software to be rewritten. Removing the restriction is
   simpler and matches X11 behavior.

---

## Security & Responsibility

This patch removes a security feature that GNOME/Wayland ships intentionally. The focus-based
clipboard restriction was designed to prevent background apps from silently reading or writing
clipboard contents.

**Apply only on systems you control** with explicit authorization. The trade-offs:

| With Patch | Without Patch |
|------------|---------------|
| VMware/VBox clipboard works | VMware/VBox clipboard broken |
| Clipboard managers work | Clipboard managers broken |
| Any app can read/write clipboard | Only focused app can access clipboard |
| Matches X11 behavior (30+ years) | "Secure" but breaks real workflows |

If you're concerned about clipboard security, consider:
- Running untrusted apps in a separate VM or container
- Not installing this patch on shared/public machines
- Using Wayland's intended security model (but losing VM clipboard)

---

## Related Issues

- [VMware open-vm-tools #510](https://github.com/vmware/open-vm-tools/issues/510)
- [VMware open-vm-tools #443](https://github.com/vmware/open-vm-tools/issues/443)
- [wlroots #2886](https://github.com/swaywm/wlroots/issues/2886)
- [GNOME Mutter #3468](https://gitlab.gnome.org/GNOME/mutter/-/issues/3468)

---

## References

- **Mutter Repository:** https://gitlab.gnome.org/GNOME/mutter
- **Target Version:** [46.2](https://gitlab.gnome.org/GNOME/mutter/-/tree/46.2)
- **Files Patched:**
  - [meta-wayland-data-device.c](https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device.c)
  - [meta-wayland-data-device-primary.c](https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device-primary.c)

---

## License

Public Domain (Unlicense). See [LICENSE](LICENSE).
