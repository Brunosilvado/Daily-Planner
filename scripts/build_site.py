"""
Assembles the deployable Pages artifact into _site/.

_site/ is never committed to git (it's listed in .gitignore and only ever
exists inside a GitHub Actions runner). The real dashboard is published at
_site/<PAGES_SLUG>/, so the random slug — and the live personal data in
data.json — never appear in this public repository's source or history.
_site/index.html (the repo-root URL) is a deliberately empty decoy page.

PAGES_SLUG must be set as a GitHub Actions secret (Settings -> Secrets and
variables -> Actions -> New repository secret). If it's missing, the build
fails loudly rather than silently publishing to a guessable path.
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_SRC = os.path.join(ROOT, "site")
OUT = os.path.join(ROOT, "_site")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_data import build as build_data  # noqa: E402


def main():
    slug = os.environ.get("PAGES_SLUG")
    if not slug or not slug.isalnum():
        raise SystemExit(
            "PAGES_SLUG secret is missing or not alphanumeric. "
            "Set it under Settings -> Secrets and variables -> Actions."
        )

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    # Decoy root page — the repo-root Pages URL shows nothing useful.
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"robots\" content=\"noindex, nofollow\">"
            "<title>Not found</title></head><body><p>Nothing here.</p></body></html>\n"
        )

    dest = os.path.join(OUT, slug)
    os.makedirs(dest)
    for name in ("index.html", "style.css", "app.js"):
        shutil.copyfile(os.path.join(SITE_SRC, name), os.path.join(dest, name))

    data = build_data()
    with open(os.path.join(dest, "data.json"), "w") as f:
        json.dump(data, f, indent=2)

    print(f"Built _site/ with dashboard at _site/<slug>/ (slug length {len(slug)}).")


if __name__ == "__main__":
    main()
