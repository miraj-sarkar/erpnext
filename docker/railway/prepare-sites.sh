#!/bin/bash
# Restore files the Railway volume hides when it mounts over /sites.
set -euo pipefail

SITES="/home/frappe/frappe-bench/sites"
BAKED_ASSETS="/home/frappe/frappe-bench/assets"
BAKED_APPS_TXT="/home/frappe/frappe-bench/built_sites/apps.txt"
BAKED_APPS_JSON="/home/frappe/frappe-bench/built_sites/apps.json"

mkdir -p "$SITES"

echo "-> Waiting for sites volume"
for _ in $(seq 1 30); do
	if touch "$SITES/.volume-ready" 2>/dev/null; then
		chown frappe:frappe "$SITES/.volume-ready" 2>/dev/null || true
		break
	fi
	sleep 1
done

# nginx try_files returns 404 for a symlink that points off the volume. Copy the
# real files (not the symlinks) onto the volume, and fill in any Frappe bundle
# the ERPNext-only rebuild dropped from assets.json.
if [ -d "$BAKED_ASSETS" ] && [ -f "$BAKED_ASSETS/assets.json" ]; then
	rm -rf "$SITES/assets"
	mkdir -p "$SITES/assets"
	/home/frappe/frappe-bench/env/bin/python - <<'PY'
import json, os, shutil

baked = "/home/frappe/frappe-bench/assets"
dest = "/home/frappe/frappe-bench/sites/assets"
apps = "/home/frappe/frappe-bench/apps"

def copy_tree(src, dst, seen):
    real = os.path.realpath(src)
    if real in seen:
        return
    seen.add(real)
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name == "node_modules":
            continue
        source = os.path.join(src, name)
        target = os.path.join(dst, name)
        if os.path.isdir(source):
            copy_tree(source, target, seen)
        elif os.path.isfile(source):
            shutil.copy2(source, target)

copy_tree(baked, dest, set())

manifest_path = os.path.join(dest, "assets.json")
manifest = json.load(open(manifest_path))
added = []
for app in ("frappe", "erpnext"):
    dist = os.path.join(apps, app, app, "public", "dist")
    if not os.path.isdir(dist):
        continue
    newest = {}
    for dirpath, dirnames, filenames in os.walk(dist):
        dirnames[:] = [name for name in dirnames if name != "node_modules"]
        rel_dir = os.path.relpath(dirpath, dist).replace(os.sep, "/")
        if rel_dir == "css-rtl" or rel_dir.startswith("css-rtl/"):
            continue
        for name in filenames:
            parts = name.split(".")
            if len(parts) < 4 or "bundle" not in parts or name.endswith(".map"):
                continue
            key = ".".join(parts[:-2] + parts[-1:])
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, dist).replace(os.sep, "/")
            mtime = os.path.getmtime(path)
            if key not in newest or mtime > newest[key][0]:
                newest[key] = (mtime, "/assets/%s/dist/%s" % (app, rel))
    for key, (_, value) in newest.items():
        if key not in manifest:
            manifest[key] = value
            added.append(key)

if added:
    with open(manifest_path, "w") as handle:
        json.dump(manifest, handle, indent=4)
        handle.write("\n")
    print("-> Added %s missing bundle keys to assets.json" % len(added))

required = ["login.bundle.css", "website.bundle.css", "frappe-web.bundle.js"]
missing = [key for key in required if key not in manifest]
if missing:
    raise SystemExit("assets.json is missing %s" % ", ".join(missing))
for key in required:
    rel = manifest[key].lstrip("/")
    file_path = os.path.join("/home/frappe/frappe-bench/sites", rel)
    if not os.path.isfile(file_path):
        raise SystemExit("%s points at missing file %s" % (key, file_path))
print("-> Login bundles are on the sites volume")
PY
	chmod -R a+rX "$SITES/assets" || true
	echo "-> Copied baked assets onto the sites volume"
else
	echo "-> Baked assets are missing; /assets will 404 until the image is rebuilt"
fi

if [ -n "${FRAPPE_REDIS_CACHE:-}" ]; then
	/home/frappe/frappe-bench/env/bin/python -c 'import os; from redis import Redis; Redis.from_url(os.environ["FRAPPE_REDIS_CACHE"]).delete("assets_json"); print("-> Cleared cached assets.json")' \
		|| echo "-> Could not clear cached assets.json"
fi

chmod 755 /home/frappe /home/frappe/frappe-bench 2>/dev/null || true

if [ ! -s "$SITES/apps.txt" ]; then
	if [ -f "$BAKED_APPS_TXT" ]; then
		cp -f "$BAKED_APPS_TXT" "$SITES/apps.txt"
	else
		printf 'frappe\nerpnext\n' > "$SITES/apps.txt"
	fi
fi

if [ ! -s "$SITES/apps.json" ] && [ -f "$BAKED_APPS_JSON" ]; then
	cp -f "$BAKED_APPS_JSON" "$SITES/apps.json"
fi

if [ ! -s "$SITES/common_site_config.json" ]; then
	echo '{}' > "$SITES/common_site_config.json"
fi

chown frappe:frappe "$SITES/apps.txt" "$SITES/common_site_config.json" 2>/dev/null || true
[ -f "$SITES/apps.json" ] && chown frappe:frappe "$SITES/apps.json" || true
chown -R frappe:frappe "$SITES" || true
