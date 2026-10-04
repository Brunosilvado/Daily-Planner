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
import hashlib
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
    shutil.copyfile(os.path.join(SITE_SRC, "style.css"), os.path.join(dest, "style.css"))
    shutil.copyfile(os.path.join(SITE_SRC, "app.js"), os.path.join(dest, "app.js"))

    # Cache-busting: phones and browsers can cache style.css/app.js
    # aggressively (GitHub Pages serves them with a far-future cache
    # header), so a deploy can silently go unnoticed on a device that
    # already has the old files cached. Tagging each with a hash of its
    # own content forces a fresh fetch whenever that file actually
    # changes, while leaving the cache alone (and the URL stable) when
    # it doesn't.
    with open(os.path.join(SITE_SRC, "style.css"), "rb") as f:
        css_hash = hashlib.sha256(f.read()).hexdigest()[:10]
    with open(os.path.join(SITE_SRC, "app.js"), "rb") as f:
        js_hash = hashlib.sha256(f.read()).hexdigest()[:10]

    with open(os.path.join(SITE_SRC, "index.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace('href="style.css"', f'href="style.css?v={css_hash}"')
    html = html.replace('src="app.js"', f'src="app.js?v={js_hash}"')
    with open(os.path.join(dest, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    data = build_data()
    with open(os.path.join(dest, "data.json"), "w") as f:
        json.dump(data, f, indent=2)

    print(f"Built _site/ with dashboard at _site/<slug>/ (slug length {len(slug)}).")


if __name__ == "__main__":
    main()
