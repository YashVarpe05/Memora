#!/usr/bin/env bash
# Copy the plugin sources and the exported vocabulary into the generated Android project.
# android-plugin/ is the source of truth; android/ is what Gradle builds.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HERE/../android/app/src/main"
mkdir -p "$APP/java/ai/memora/app" "$APP/assets"
cp "$HERE"/*.java "$APP/java/ai/memora/app/"
cp "$HERE/document_types.tsv" "$APP/assets/document_types.tsv"
echo "synced $(ls "$HERE"/*.java | wc -l) Java files and document_types.tsv"
