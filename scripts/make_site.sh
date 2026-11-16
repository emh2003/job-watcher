#!/usr/bin/env bash
# Copies what the website needs into _site/: the pages and the two data files.
# The raw files stay in the repository and are not published.
set -euo pipefail
rm -rf _site
mkdir -p _site/data
cp index.html browse.html market.html app.js style.css sw.js manifest.webmanifest _site/
cp -r icons _site/
cp data/history.csv data/status.json _site/data/ 2>/dev/null || echo "no data files yet"
touch _site/.nojekyll
