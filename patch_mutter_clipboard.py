#!/usr/bin/env python3
"""
patch_mutter_clipboard.py

Strict patcher for GNOME Mutter to remove Wayland clipboard focus restrictions.

This patch removes the focus checks that prevent clipboard operations from working
when the requesting application is not focused. X11 never had these restrictions
and worked fine for 30+ years. This patch restores that behavior.

Target Version: Mutter 46.2 (Ubuntu 24.04 LTS)
Repository: https://gitlab.gnome.org/GNOME/mutter

Files patched:
  - src/wayland/meta-wayland-data-device.c         (CLIPBOARD)
  - src/wayland/meta-wayland-data-device-primary.c (PRIMARY selection / middle-click)

What this fixes:
  - VMware clipboard integration on Wayland hosts
  - VirtualBox clipboard integration
  - Clipboard managers
  - Any application that needs background clipboard access

Usage:
  python3 patch_mutter_clipboard.py /path/to/mutter-46.2

This script:
  - Validates the source tree matches mutter 46.2 layout (strict sentinels)
  - REFUSES TO RUN if any *.bak backup already exists (safety)
  - Creates *.bak backups before patching
  - Removes focus checks and modifies notification loops
  - Shows diff preview of changes
"""

import sys
import os
import re
import shutil
import subprocess
import difflib

# =============================================================================
# CONFIGURATION - Mutter 46.2 Specific
# =============================================================================

MUTTER_VERSION = "46.2"
GITLAB_BASE = f"https://gitlab.gnome.org/GNOME/mutter/-/blob/{MUTTER_VERSION}"

REQUIRED_FILES = {
    "data-device": "src/wayland/meta-wayland-data-device.c",
    "data-device-primary": "src/wayland/meta-wayland-data-device-primary.c",
}

# GitLab links for reference (validated against 46.2)
HELP_LINKS = {
    "data-device": f"{GITLAB_BASE}/src/wayland/meta-wayland-data-device.c",
    "data-device-primary": f"{GITLAB_BASE}/src/wayland/meta-wayland-data-device-primary.c",
}

# =============================================================================
# SENTINELS - Validate we're looking at mutter 46.2 layout
# =============================================================================

SENTINELS = {
    "data-device": [
        # Function signatures we expect
        r"^static void\s+data_device_set_selection\s*\(",
        r"^static void\s+owner_changed_cb\s*\(",
        r"^void\s+meta_wayland_data_device_sync_focus\s*\(",
        # The focus check pattern we're removing
        r"meta_wayland_seat_get_input_focus_client\s*\(\s*seat\s*\)",
        # The focus_resource_list we need to change
        r"&data_device->focus_resource_list",
    ],
    "data-device-primary": [
        # Function signatures we expect
        r"^static void\s+primary_device_set_selection\s*\(",
        r"^static void\s+owner_changed_cb\s*\(",
        r"^void\s+meta_wayland_data_device_primary_sync_focus\s*\(",
        # The focus check pattern
        r"meta_wayland_seat_get_input_focus_client\s*\(\s*seat\s*\)",
        # The focus_resource_list
        r"&data_device->focus_resource_list",
    ],
}

# Patch marker tag
PATCH_TAG = "VMWARE_CLIPBOARD_PATCH"

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def die(msg, filekey=None):
    """Print error and exit."""
    print(f"\n[ERROR] {msg}\n", file=sys.stderr)
    if filekey and filekey in HELP_LINKS:
        print(f"Compare against upstream {MUTTER_VERSION}:", file=sys.stderr)
        print(f"  {HELP_LINKS[filekey]}", file=sys.stderr)
    print(f"\nThis patcher targets mutter {MUTTER_VERSION} specifically.", file=sys.stderr)
    print("If your version differs, adapt the patch manually.\n", file=sys.stderr)
    sys.exit(1)


def detect_version(root):
    """Try to detect the checked-out mutter version."""
    try:
        p = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=root, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=5
        )
        if p.returncode == 0:
            return p.stdout.strip()
        # Try meson.build version
        meson_path = os.path.join(root, "meson.build")
        if os.path.exists(meson_path):
            with open(meson_path) as f:
                content = f.read()
                m = re.search(r"version\s*:\s*'(\d+\.\d+)", content)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None


def read_file(path):
    """Read file content."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_with_backup(path, new_content):
    """Write file with .bak backup. Refuses if backup exists."""
    backup = path + ".bak"
    if os.path.exists(backup):
        die(f"Backup already exists: {backup}\n"
            "To protect your previous backup, this run aborts.\n"
            "Move/rename the existing .bak and re-run.", None)
    shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)


def check_sentinels(path, content, patterns, filekey):
    """Verify all sentinel patterns exist in the file."""
    for pat in patterns:
        if not re.search(pat, content, flags=re.MULTILINE):
            die(f"Sentinel not found in {path}:\n  pattern: {pat}\n"
                f"File does not match expected mutter {MUTTER_VERSION} layout.",
                filekey=filekey)


def show_diff(before, after, label, max_lines=100):
    """Show unified diff of changes."""
    diff = list(difflib.unified_diff(
        before.splitlines(keepends=False),
        after.splitlines(keepends=False),
        fromfile=f"{label} (before)",
        tofile=f"{label} (after)",
        lineterm=""
    ))
    if not diff:
        print(f"[SKIP] {label}: already patched or no changes needed")
        return False
    print(f"\n[DIFF] {label}:")
    for i, line in enumerate(diff):
        if i >= max_lines:
            print("  ... (diff truncated)")
            break
        print(line)
    return True


# =============================================================================
# PATCH: meta-wayland-data-device.c
# =============================================================================

def patch_data_device(text):
    """
    Patch meta-wayland-data-device.c to remove focus restrictions.

    Changes (mutter 46.2 line numbers):
    1. Remove focus check in data_device_set_selection() [lines 1064-1070]
       https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device.c#L1064-1070

    2. Remove focus check in owner_changed_cb() AND notify ALL clients [lines 1107-1127]
       https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device.c#L1107-1127

       The original code only notifies focused client via focus_resource_list.
       We need to notify ALL clients by iterating over BOTH resource_list AND focus_resource_list.
    """

    if PATCH_TAG in text:
        return text  # Already patched

    # =========================================================================
    # PATCH 1: Remove focus check in data_device_set_selection()
    # Lines 1064-1070 in 46.2
    # =========================================================================
    # Original:
    #   if (wl_resource_get_client (resource) !=
    #       meta_wayland_seat_get_input_focus_client (seat))
    #     {
    #       if (source)
    #         meta_wayland_data_source_cancel (source);
    #       return;
    #     }
    #
    #   /* FIXME: Store serial and check against incoming serial here. */

    pattern1 = (
        r"(    \}\n\n)"  # End of the actions check block
        r"  if \(wl_resource_get_client \(resource\) !=\n"
        r"      meta_wayland_seat_get_input_focus_client \(seat\)\)\n"
        r"    \{\n"
        r"      if \(source\)\n"
        r"        meta_wayland_data_source_cancel \(source\);\n"
        r"      return;\n"
        r"    \}\n\n"
        r"(  /\* FIXME: Store serial)"
    )

    replacement1 = (
        r"\1"
        f"  /* === {PATCH_TAG} ===\n"
        "   * REMOVED: Focus check that blocked clipboard writes from unfocused apps.\n"
        "   * X11 never had this restriction. VMware, VirtualBox, clipboard managers\n"
        "   * all depend on background clipboard access.\n"
        "   * Original code (lines 1064-1070):\n"
        "   *   if (wl_resource_get_client (resource) !=\n"
        "   *       meta_wayland_seat_get_input_focus_client (seat))\n"
        "   *     { if (source) meta_wayland_data_source_cancel (source); return; }\n"
        f"   * === /{PATCH_TAG} === */\n\n"
        r"\2"
    )

    text, count1 = re.subn(pattern1, replacement1, text, count=1)
    if count1 == 0:
        die("PATCH 1 failed: Could not find focus check in data_device_set_selection()\n"
            "Expected pattern at lines 1064-1070", "data-device")

    # =========================================================================
    # PATCH 2: Remove focus check AND notify ALL clients in owner_changed_cb()
    # Lines 1107-1127 in 46.2
    # =========================================================================
    # Original only notifies focus_resource_list (focused client only).
    # We need to notify BOTH resource_list AND focus_resource_list (all clients).
    #
    # Resources are split between two lists:
    #   - resource_list: non-focused clients
    #   - focus_resource_list: focused client only
    # We must iterate BOTH to notify everyone.

    pattern2 = (
        r"(  MetaWaylandSeat \*seat = compositor->seat;\n)"
        r"  struct wl_resource \*data_device_resource;\n"
        r"  struct wl_client \*focus_client;\n\n"
        r"  focus_client = meta_wayland_seat_get_input_focus_client \(seat\);\n"
        r"  if \(!focus_client\)\n"
        r"    return;\n\n"
        r"  if \(selection_type == META_SELECTION_CLIPBOARD\)\n"
        r"    \{\n"
        r"      wl_resource_for_each \(data_device_resource,\n"
        r"                            &data_device->focus_resource_list\)\n"
        r"        \{\n"
        r"          struct wl_resource \*offer = NULL;\n\n"
        r"          if \(new_owner\)\n"
        r"            \{\n"
        r"              offer = create_and_send_clipboard_offer \(data_device,\n"
        r"                                                       data_device_resource\);\n"
        r"            \}\n\n"
        r"          wl_data_device_send_selection \(data_device_resource, offer\);\n"
        r"        \}\n"
        r"    \}\n"
        r"\}"
    )

    replacement2 = (
        r"\1"
        "  struct wl_resource *data_device_resource;\n\n"
        f"  /* === {PATCH_TAG} ===\n"
        "   * REMOVED: Focus check that blocked clipboard notifications to unfocused apps.\n"
        "   * CHANGED: Now notify ALL clients, not just the focused one.\n"
        "   * Resources are split between resource_list (unfocused) and focus_resource_list (focused),\n"
        "   * so we must iterate BOTH lists to notify everyone.\n"
        "   * Original code only iterated focus_resource_list.\n"
        f"   * === /{PATCH_TAG} === */\n\n"
        "  if (selection_type == META_SELECTION_CLIPBOARD)\n"
        "    {\n"
        "      /* Notify unfocused clients (resource_list) */\n"
        "      wl_resource_for_each (data_device_resource,\n"
        "                            &data_device->resource_list)\n"
        "        {\n"
        "          struct wl_resource *offer = NULL;\n\n"
        "          if (new_owner)\n"
        "            {\n"
        "              offer = create_and_send_clipboard_offer (data_device,\n"
        "                                                       data_device_resource);\n"
        "            }\n\n"
        "          wl_data_device_send_selection (data_device_resource, offer);\n"
        "        }\n\n"
        "      /* Notify focused client (focus_resource_list) */\n"
        "      wl_resource_for_each (data_device_resource,\n"
        "                            &data_device->focus_resource_list)\n"
        "        {\n"
        "          struct wl_resource *offer = NULL;\n\n"
        "          if (new_owner)\n"
        "            {\n"
        "              offer = create_and_send_clipboard_offer (data_device,\n"
        "                                                       data_device_resource);\n"
        "            }\n\n"
        "          wl_data_device_send_selection (data_device_resource, offer);\n"
        "        }\n"
        "    }\n"
        "}"
    )

    text, count2 = re.subn(pattern2, replacement2, text, count=1)
    if count2 == 0:
        die("PATCH 2 failed: Could not find owner_changed_cb() clipboard notification block\n"
            "Expected pattern at lines 1107-1127", "data-device")

    return text


# =============================================================================
# PATCH: meta-wayland-data-device-primary.c
# =============================================================================

def patch_data_device_primary(text):
    """
    Patch meta-wayland-data-device-primary.c to remove focus restrictions.

    Changes (mutter 46.2 line numbers):
    1. Remove focus check in primary_device_set_selection() [lines 184-190]
       https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device-primary.c#L184-190

    2. Remove focus check in owner_changed_cb() AND notify ALL clients [lines 212-233]
       https://gitlab.gnome.org/GNOME/mutter/-/blob/46.2/src/wayland/meta-wayland-data-device-primary.c#L212-233
    """

    if PATCH_TAG in text:
        return text  # Already patched

    # =========================================================================
    # PATCH 1: Remove focus check in primary_device_set_selection()
    # Lines 184-190 in 46.2
    # =========================================================================
    # Original:
    #   if (wl_resource_get_client (resource) !=
    #       meta_wayland_seat_get_input_focus_client (seat))
    #     {
    #       if (source)
    #         meta_wayland_data_source_cancel (source);
    #       return;
    #     }

    pattern1 = (
        r"(  if \(source_resource\)\n"
        r"    source = wl_resource_get_user_data \(source_resource\);\n\n)"
        r"  if \(wl_resource_get_client \(resource\) !=\n"
        r"      meta_wayland_seat_get_input_focus_client \(seat\)\)\n"
        r"    \{\n"
        r"      if \(source\)\n"
        r"        meta_wayland_data_source_cancel \(source\);\n"
        r"      return;\n"
        r"    \}\n\n"
        r"(  meta_wayland_data_device_primary_set_selection)"
    )

    replacement1 = (
        r"\1"
        f"  /* === {PATCH_TAG} ===\n"
        "   * REMOVED: Focus check that blocked primary selection writes from unfocused apps.\n"
        "   * X11 never had this restriction.\n"
        "   * Original code (lines 184-190):\n"
        "   *   if (wl_resource_get_client (resource) !=\n"
        "   *       meta_wayland_seat_get_input_focus_client (seat))\n"
        "   *     { if (source) meta_wayland_data_source_cancel (source); return; }\n"
        f"   * === /{PATCH_TAG} === */\n\n"
        r"\2"
    )

    text, count1 = re.subn(pattern1, replacement1, text, count=1)
    if count1 == 0:
        die("PATCH 1 failed: Could not find focus check in primary_device_set_selection()\n"
            "Expected pattern at lines 184-190", "data-device-primary")

    # =========================================================================
    # PATCH 2: Remove focus check AND notify ALL clients in owner_changed_cb()
    # Lines 212-233 in 46.2
    # =========================================================================

    pattern2 = (
        r"(  MetaWaylandSeat \*seat = compositor->seat;\n)"
        r"  struct wl_resource \*data_device_resource;\n"
        r"  struct wl_client \*focus_client;\n\n"
        r"  focus_client = meta_wayland_seat_get_input_focus_client \(seat\);\n"
        r"  if \(!focus_client\)\n"
        r"    return;\n\n"
        r"  if \(selection_type == META_SELECTION_PRIMARY\)\n"
        r"    \{\n"
        r"      wl_resource_for_each \(data_device_resource, &data_device->focus_resource_list\)\n"
        r"        \{\n"
        r"          struct wl_resource \*offer = NULL;\n\n"
        r"          if \(new_owner\)\n"
        r"            \{\n"
        r"              offer = create_and_send_primary_offer \(data_device,\n"
        r"                                                     data_device_resource\);\n"
        r"            \}\n\n"
        r"          zwp_primary_selection_device_v1_send_selection \(data_device_resource,\n"
        r"                                                          offer\);\n"
        r"        \}\n"
        r"    \}\n"
        r"\}"
    )

    replacement2 = (
        r"\1"
        "  struct wl_resource *data_device_resource;\n\n"
        f"  /* === {PATCH_TAG} ===\n"
        "   * REMOVED: Focus check that blocked primary selection notifications.\n"
        "   * CHANGED: Now notify ALL clients, not just the focused one.\n"
        f"   * === /{PATCH_TAG} === */\n\n"
        "  if (selection_type == META_SELECTION_PRIMARY)\n"
        "    {\n"
        "      /* Notify unfocused clients (resource_list) */\n"
        "      wl_resource_for_each (data_device_resource, &data_device->resource_list)\n"
        "        {\n"
        "          struct wl_resource *offer = NULL;\n\n"
        "          if (new_owner)\n"
        "            {\n"
        "              offer = create_and_send_primary_offer (data_device,\n"
        "                                                     data_device_resource);\n"
        "            }\n\n"
        "          zwp_primary_selection_device_v1_send_selection (data_device_resource,\n"
        "                                                          offer);\n"
        "        }\n\n"
        "      /* Notify focused client (focus_resource_list) */\n"
        "      wl_resource_for_each (data_device_resource, &data_device->focus_resource_list)\n"
        "        {\n"
        "          struct wl_resource *offer = NULL;\n\n"
        "          if (new_owner)\n"
        "            {\n"
        "              offer = create_and_send_primary_offer (data_device,\n"
        "                                                     data_device_resource);\n"
        "            }\n\n"
        "          zwp_primary_selection_device_v1_send_selection (data_device_resource,\n"
        "                                                          offer);\n"
        "        }\n"
        "    }\n"
        "}"
    )

    text, count2 = re.subn(pattern2, replacement2, text, count=1)
    if count2 == 0:
        die("PATCH 2 failed: Could not find owner_changed_cb() primary selection notification block\n"
            "Expected pattern at lines 212-233", "data-device-primary")

    return text


# =============================================================================
# MAIN
# =============================================================================

def main():
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} /path/to/mutter-{MUTTER_VERSION}")
        print(f"\nThis patcher targets mutter {MUTTER_VERSION} specifically.")
        print("Clone and checkout:")
        print(f"  git clone https://gitlab.gnome.org/GNOME/mutter.git")
        print(f"  cd mutter && git checkout {MUTTER_VERSION}")
        sys.exit(1)

    root = os.path.abspath(sys.argv[1])

    # Check version
    detected = detect_version(root)
    if detected:
        print(f"[info] Detected version: {detected}")
        if detected != MUTTER_VERSION and not detected.startswith(MUTTER_VERSION.split('.')[0]):
            print(f"[WARN] This patcher targets {MUTTER_VERSION}, but detected {detected}")
            print("       Proceeding anyway, but sentinels may fail if layout differs.")

    # Verify required files exist
    paths = {}
    for key, relpath in REQUIRED_FILES.items():
        fullpath = os.path.join(root, relpath)
        if not os.path.isfile(fullpath):
            die(f"Missing required file: {fullpath}\n"
                f"Ensure you're pointing at a mutter {MUTTER_VERSION} source tree.", key)
        paths[key] = fullpath

    # Check for existing backups (refuse to overwrite)
    existing_baks = [p + ".bak" for p in paths.values() if os.path.exists(p + ".bak")]
    if existing_baks:
        msg = ["Refusing to proceed because backups already exist:"]
        msg += [f"  - {b}" for b in existing_baks]
        msg.append("Move/rename these .bak files and re-run.")
        die("\n".join(msg), None)

    # Read and validate files
    texts = {}
    for key, path in paths.items():
        content = read_file(path)
        check_sentinels(path, content, SENTINELS[key], key)
        texts[key] = content

    print(f"\n[OK] Source tree validated against mutter {MUTTER_VERSION} layout\n")

    # Apply patches
    patched = {}
    patched["data-device"] = patch_data_device(texts["data-device"])
    patched["data-device-primary"] = patch_data_device_primary(texts["data-device-primary"])

    # Write files with backups
    for key, path in paths.items():
        if patched[key] != texts[key]:
            write_with_backup(path, patched[key])
            print(f"[OK] Patched {path}")
            print(f"     Backup: {path}.bak")
            show_diff(texts[key], patched[key], os.path.basename(path))
        else:
            print(f"[SKIP] {path}: already patched")

    print(f"""
================================================================================
PATCHING COMPLETE
================================================================================

Patches applied:
  1. data_device_set_selection(): Removed focus check (any client can set clipboard)
  2. primary_device_set_selection(): Removed focus check (any client can set primary)
  3. owner_changed_cb() (clipboard): Now notifies ALL clients (both lists)
  4. owner_changed_cb() (primary): Now notifies ALL clients (both lists)

Next steps:

1) Install build dependencies:
   sudo apt build-dep mutter

2) Build mutter:
   cd {root}
   meson setup build --prefix=/usr --buildtype=release
   ninja -C build

3) Install (backup your system first!):
   sudo ninja -C build install

4) Restart GNOME Shell:
   - Log out and log back in, OR
   - killall -3 gnome-shell (on X11), OR
   - Reboot

5) Prevent apt from overwriting your patched mutter:
   sudo apt-mark hold mutter mutter-common libmutter-14-0

To revert:
   sudo apt-mark unhold mutter mutter-common libmutter-14-0
   sudo apt install --reinstall mutter mutter-common libmutter-14-0
""")


if __name__ == "__main__":
    main()
