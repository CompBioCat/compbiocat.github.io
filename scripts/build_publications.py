#!/usr/bin/env python3
"""Build the publication and preprint lists from the group's BibTeX exports.

Reads   data/publications.yml  (configuration and editorial decisions)
        data/*.bib             (the ORCID exports named in that file)
Writes  _publications.md       (every publication, under ### year headings)
        _preprints.md          (the preprint section on its own, for reuse)

Run after updating either .bib file:

    python scripts/build_publications.py

Only the standard library plus PyYAML is required — deliberately, so nobody has
to install a BibTeX library to update the site.

The two exports are in different formats. Ferran's is partly hand-maintained
with multi-line entries; Marc's is a machine export with one entry per line,
each indented by a space and separated by lines containing a bare comma. The
parser below handles both by anchoring entries to `@type{` at the start of a
line (optionally indented) and matching braces from there — NOT by splitting on
"@", which also appears inside field values.
"""

from __future__ import annotations

import difflib
import html
import re
import sys
import unicodedata
from itertools import groupby
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is missing. Install it with:  python3 -m pip install pyyaml")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import warn_if_preview_running   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = DATA / "publications.yml"

# Preprint server DOI prefixes.
PREPRINT_DOI = ("10.26434", "10.1101", "10.48550", "10.21203", "10.22541")
PREPRINT_WORDS = ("chemrxiv", "biorxiv", "arxiv", "research square", "researchsquare",
                  "preprint")

ENTRY_RE = re.compile(r"(?:^|\n)[ \t]*@(\w+)\s*\{")

# Surname particles, so "Max von Delius" and "von Delius, Max" agree.
PARTICLES = {"von", "van", "de", "der", "den", "del", "della", "di", "da",
             "dos", "du", "la", "le", "el", "al", "bin", "ter", "ten"}

warnings: list[str] = []
notes: list[str] = []


# --------------------------------------------------------------------------- #
#  BibTeX parsing
# --------------------------------------------------------------------------- #

def split_entries(text: str) -> list[tuple[str, str]]:
    """Yield (type, body) for each entry, matching braces from the opening one."""
    out = []
    for m in ENTRY_RE.finditer(text):
        etype = m.group(1).lower()
        start = text.index("{", m.start())
        depth, j = 0, start
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append((etype, text[start:j + 1]))
    return out


def field(entry: str, *names: str) -> str:
    """First non-empty value among `names`. Handles {braced}, "quoted" and bare."""
    for name in names:
        for m in re.finditer(r"\b" + name + r"\s*=\s*", entry, re.I):
            k = m.end()
            if k < len(entry) and entry[k] == "{":
                depth, j = 0, k
                while j < len(entry):
                    if entry[j] == "{":
                        depth += 1
                    elif entry[j] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                value = entry[k + 1:j]
            else:
                m2 = re.match(r'"([^"]*)"|([^,}\n]+)', entry[k:])
                value = (m2.group(1) or m2.group(2)) if m2 else ""
            value = tidy(value)
            if value:
                return value
    return ""


# LaTeX accent commands -> Unicode combining characters. The exports write
# names as "Calv{\'{o}}-Tusell" and "Gri{\~{n}}{\'{a}}n-Ferr{\'{e}}". These must
# be decoded BEFORE braces are stripped, or the accent is lost and the bare
# escape ends up on the page.
COMBINING = {
    "'": "\u0301",   # acute
    "`": "\u0300",   # grave
    "^": "\u0302",   # circumflex
    '"': "\u0308",   # diaeresis
    "~": "\u0303",   # tilde
    "=": "\u0304",   # macron
    ".": "\u0307",   # dot above
    "c": "\u0327",   # cedilla
    "v": "\u030C",   # caron
    "u": "\u0306",   # breve
    "H": "\u030B",   # double acute
    "k": "\u0328",   # ogonek
    "r": "\u030A",   # ring above
    "d": "\u0323",   # dot below
    "b": "\u0331",   # macron below
}

# Standalone commands. Matched with re.escape and a trailing letter guard, so
# \textendash is never matched as \t, and longest-first so \upalpha is not
# shadowed by \up.
LATEX_LITERALS = [
    (r"\textendash", "\u2013"), (r"\textemdash", "\u2014"),
    (r"\textquotesingle", "\u2019"), (r"\textquotedblleft", "\u201c"),
    (r"\textquotedblright", "\u201d"),
    (r"\upalpha", "\u03b1"), (r"\upbeta", "\u03b2"), (r"\upgamma", "\u03b3"),
    (r"\updelta", "\u03b4"), (r"\upepsilon", "\u03b5"), (r"\upeta", "\u03b7"),
    (r"\upkappa", "\u03ba"), (r"\uplambda", "\u03bb"), (r"\upmu", "\u03bc"),
    (r"\upnu", "\u03bd"), (r"\uppi", "\u03c0"), (r"\uprho", "\u03c1"),
    (r"\upsigma", "\u03c3"), (r"\uptau", "\u03c4"), (r"\upomega", "\u03c9"),
    (r"\alpha", "\u03b1"), (r"\beta", "\u03b2"), (r"\gamma", "\u03b3"),
    (r"\delta", "\u03b4"), (r"\epsilon", "\u03b5"), (r"\eta", "\u03b7"),
    (r"\kappa", "\u03ba"), (r"\lambda", "\u03bb"), (r"\mu", "\u03bc"),
    (r"\nu", "\u03bd"), (r"\pi", "\u03c0"), (r"\rho", "\u03c1"),
    (r"\sigma", "\u03c3"), (r"\tau", "\u03c4"), (r"\omega", "\u03c9"),
    (r"\ss", "\u00df"), (r"\aa", "\u00e5"), (r"\AA", "\u00c5"),
    (r"\oe", "\u0153"), (r"\OE", "\u0152"), (r"\ae", "\u00e6"),
    (r"\AE", "\u00c6"), (r"\o", "\u00f8"), (r"\O", "\u00d8"),
    (r"\l", "\u0142"), (r"\L", "\u0141"),
    (r"\&", "&"), (r"\%", "%"), (r"\$", "$"), (r"\#", "#"), (r"\_", "_"),
]
LATEX_LITERALS.sort(key=lambda kv: -len(kv[0]))

ACCENT_RE = re.compile(
    r"\\(['`^\"~=.cvuHkrdb])\s*\{\s*([A-Za-z])\s*\}"   # \'{o}  \c{C}
    r"|\\(['`^\"~=.])\s*([A-Za-z])"                     # \'o
)


def delatex(s: str) -> str:
    """Decode LaTeX accents and literal commands to Unicode."""
    if "\\" not in s:
        return s
    # \i and \j are the dotless forms used under accents; the accent belongs on
    # the ordinary letter, so "\'{\i}" must give "í" rather than "ı".
    s = re.sub(r"\{\\i\}|\\i(?![A-Za-z])", "i", s)
    s = re.sub(r"\{\\j\}|\\j(?![A-Za-z])", "j", s)
    s = re.sub(r"\\hspace\s*\{[^}]*\}", "", s)

    def accent(m):
        cmd = m.group(1) or m.group(3)
        letter = m.group(2) or m.group(4)
        return unicodedata.normalize("NFC", letter + COMBINING.get(cmd, ""))

    # Twice: "{\'{a}}n" style nesting can leave a second layer to resolve.
    for _ in range(2):
        s = ACCENT_RE.sub(accent, s)

    for cmd, char in LATEX_LITERALS:
        # The "not followed by a letter" guard stops \o matching inside
        # \omega, but must not apply to symbol commands: in "Zn\&Cu" the
        # ampersand is legitimately followed by a letter.
        guard = r"(?![A-Za-z])" if cmd[-1].isalpha() else ""
        s = re.sub(re.escape(cmd) + guard, char, s)
    return s


def tidy(s: str) -> str:
    """Strip the markup these exports carry: HTML tags, LaTeX braces, whitespace."""
    # Superscripts and subscripts are written across several lines in these
    # exports, e.g. "C\n    <sub>60</sub>\n    fullerene". Stripping the tags
    # generically leaves "C 60 fullerene", so they are handled first: the
    # whitespace BEFORE the tag is consumed (a subscript never has a space in
    # front of it) while the whitespace after is left to collapse into one
    # space, which is usually what the text wants.
    s = re.sub(r"\s*<(sub|sup)>\s*(.*?)\s*</\1>", r"\2", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = delatex(s)                  # must precede the brace strip below
    s = s.replace("--", "–")
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\s+([,;:.])", r"\1", s)
    return s


def normalise(s: str) -> str:
    """Accent-free, punctuation-free lowercase, for comparing titles and names."""
    s = unicodedata.normalize("NFKD", tidy(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def apply_title_fixes(records, cfg) -> None:
    """Literal repairs from publications.yml, for damage no rule generalises.

    Applied to titles, journal names AND author lists — the export lost
    characters in all three.
    """
    fixes = cfg.get("title_fixes") or []
    used = {i: 0 for i, _ in enumerate(fixes)}
    for r in records:
        for i, f in enumerate(fixes):
            m, rep = str(f["match"]), str(f.get("replace", ""))
            for key in ("title", "journal", "authors"):
                if m in r[key]:
                    r[key] = r[key].replace(m, rep)
                    used[i] += 1
    for i, f in enumerate(fixes):
        if used[i]:
            notes.append(f"applied title fix ({used[i]}x): {f['match']!r} -> {f.get('replace')!r}")
        else:
            warnings.append(f"title fix matched nothing and may be stale: {f['match']!r}")


def flag_corrupt_text(records) -> None:
    """Warn about characters lost in the BibTeX export itself.

    Greek letters and dashes come through as "?" in places — e.g. "p38?",
    "Diels?Alder". These are wrong in the source files, and guessing which
    character was meant would be inventing content, so they are reported for
    the group to correct at source or via title_fixes.
    """
    hits = []
    for r in records:
        # A trailing "?" is legitimate — several titles are questions — so it is
        # stripped before testing. Author lists are checked too: that is where
        # "Zale?ny" for Zaleśny turned up.
        if "?" in r["title"].rstrip("?") or "\ufffd" in r["title"]:
            hits.append(f"{r['year']} title:   {r['title'][:58]}")
        if "?" in r["authors"] or "\ufffd" in r["authors"]:
            bad = [a for a in re.split(r"\s+and\s+", r["authors"]) if "?" in a]
            hits.append(f"{r['year']} authors: {', '.join(bad)[:58]}")
    if hits:
        warnings.append(f"{len(hits)} record(s) contain a '?' where the export lost a "
                        f"character (Greek letters, accents, primes, en dashes). Fix in "
                        f"the .bib or add a title_fixes entry:")
        for h in hits:
            warnings.append(f"    {h}")


def clean_doi(raw: str) -> str:
    d = raw.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d.rstrip(" .")


# --------------------------------------------------------------------------- #
#  Authors
# --------------------------------------------------------------------------- #

def split_authors(raw: str) -> list[tuple[str, str]]:
    """Return [(surname, initials)] from a BibTeX author field.

    Handles both "Surname, First M" and "First M Surname", which both occur
    across the two files.
    """
    people = []
    for part in re.split(r"\s+and\s+", raw):
        part = tidy(part)
        if not part:
            continue
        if "," in part:
            surname, given = part.split(",", 1)
        else:
            bits = part.split()
            if len(bits) == 1:
                surname, given = bits[0], ""
            else:
                # Lowercase particles belong to the surname. Without this,
                # "Max von Delius" yields "Delius, M. v." while the other
                # file's "von Delius, Max" yields "von Delius, M." — the same
                # person rendered two different ways.
                i = len(bits) - 1
                while i > 0 and bits[i - 1].lower() in PARTICLES:
                    i -= 1
                surname, given = " ".join(bits[i:]), " ".join(bits[:i])
        initials = " ".join(f"{w[0]}." for w in given.split() if w and w[0].isalpha())
        people.append((surname.strip(), initials.strip()))
    return people


def build_member_matchers(cfg) -> list[tuple[set, str]]:
    out = []
    for m in cfg.get("group_members", []):
        variants = {normalise(v) for v in str(m["surname"]).split("|") if v.strip()}
        out.append((variants, str(m.get("initial", "")).upper()))
    return out


def is_member(surname: str, initials: str, matchers) -> bool:
    key = normalise(surname)
    first = (initials[:1] or "").upper()
    for variants, initial in matchers:
        if key in variants and (not initial or not first or first == initial):
            return True
    return False


def format_authors(raw: str, matchers) -> str:
    people = split_authors(raw)
    if not people:
        return ""
    out = []
    for surname, initials in people:
        name = f"{surname}, {initials}".rstrip(", ") if initials else surname
        name = esc(name)
        out.append(f"<strong>{name}</strong>"
                   if is_member(surname, initials, matchers) else name)
    return "; ".join(out)


def esc(s: str) -> str:
    """HTML-escape. These entries are emitted as raw HTML, so escaping markdown
    and converting it back was both unnecessary and lossy — it mangled a title
    containing an asterisk."""
    return html.escape(s, quote=False)


# --------------------------------------------------------------------------- #
#  Records
# --------------------------------------------------------------------------- #

def completeness(r: dict) -> int:
    """Higher is better. Used to pick which of two duplicates to keep."""
    score = 0
    for key, points in (("doi", 4), ("journal", 3), ("volume", 1), ("pages", 1), ("authors", 2)):
        if r.get(key):
            score += points
    # Angewandte publishes each paper twice; prefer the International Edition,
    # which is the one that gets cited.
    if "international edition" in r["journal"].lower():
        score += 2
    if re.search(r"angewandte chemie$", r["journal"].strip(), re.I):
        score -= 1
    return score


def load_records(cfg) -> list[dict]:
    records = []
    for name in cfg["sources"]:
        path = DATA / name
        if not path.exists():
            warnings.append(f"source missing: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(errors="replace")
        found = split_entries(text)
        print(f"  {name:<30} {len(found):>4} entries")
        for etype, body in found:
            records.append({
                "source": name,
                "type": etype,
                "title": field(body, "title"),
                "authors": field(body, "author", "authors"),
                "journal": field(body, "journal", "journaltitle", "booktitle"),
                "volume": field(body, "volume"),
                "pages": field(body, "pages", "page"),
                "year": field(body, "year", "date")[:4],
                "doi": clean_doi(field(body, "doi")),
                "url": field(body, "url"),
            })
    return records


def is_preprint(r: dict) -> bool:
    if r["doi"].startswith(PREPRINT_DOI):
        return True
    blob = f"{r['journal']} {r['url']}".lower()
    return any(w in blob for w in PREPRINT_WORDS)


def dedupe(records: list[dict], label: str) -> list[dict]:
    """Deduplicate by DOI first, then by normalised title.

    The two PIs co-author heavily, so most papers appear in both files. Title
    matching is the second pass because the same paper can carry different DOIs
    — Angewandte's two editions being the clearest case.
    """
    by_doi: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    order: list[dict] = []
    dropped = {"doi": 0, "title": 0}

    for r in records:
        doi, title = r["doi"], normalise(r["title"])
        existing = by_doi.get(doi) if doi else None
        if existing is None and title:
            existing = by_title.get(title)
        if existing is not None:
            dropped["doi" if doi and doi in by_doi else "title"] += 1
            # keep whichever record carries more information
            if completeness(r) > completeness(existing):
                order[order.index(existing)] = r
                if doi:
                    by_doi[doi] = r
                if title:
                    by_title[title] = r
            continue
        if doi:
            by_doi[doi] = r
        if title:
            by_title[title] = r
        order.append(r)

    notes.append(f"{label}: {len(order)} kept, "
                 f"{dropped['doi']} duplicate DOIs and {dropped['title']} duplicate titles removed")
    return order


def partition_preprints(preprints, publications, cfg):
    """Split preprints into (still unpublished, published elsewhere).

    A preprint whose paper has since appeared should show in neither section.
    Matched three ways: the config's explicit list, an exact title match against
    the publication list, then a 90% similarity match. The explicit list exists
    because titles routinely change on publication, which defeats both automatic
    passes.
    """
    conf = cfg.get("preprints") or {}
    published_dois = {clean_doi(e["doi"]) for e in (conf.get("published_elsewhere") or [])
                      if e.get("doi")}
    published_titles = {normalise(e["title"]) for e in (conf.get("published_elsewhere") or [])
                        if e.get("title")}
    pub_titles = [normalise(p["title"]) for p in publications if p["title"]]

    unpublished, published = [], []
    for r in preprints:
        title = normalise(r["title"])
        if r["doi"] and r["doi"] in published_dois:
            published.append((r, "listed in publications.yml"))
        elif title and title in published_titles:
            published.append((r, "listed in publications.yml (by title)"))
        elif title and title in pub_titles:
            published.append((r, "exact title match to a published paper"))
        elif title and difflib.get_close_matches(title, pub_titles, n=1, cutoff=0.90):
            published.append((r, "90% title match to a published paper"))
        else:
            unpublished.append(r)
    return unpublished, published


# --------------------------------------------------------------------------- #
#  Rendering
# --------------------------------------------------------------------------- #

HEADER = ("<!-- GENERATED by scripts/build_publications.py from data/*.bib and\n"
          "     data/publications.yml. Hand edits will be overwritten. -->\n")


def venue(r: dict) -> str:
    bits = []
    if r["journal"]:
        bits.append(f"<em>{esc(r['journal'])}</em>")
    if r["year"]:
        bits.append(esc(r["year"]))
    if r["volume"]:
        bits.append(f"<strong>{esc(r['volume'])}</strong>")
    if r["pages"]:
        bits.append(esc(r["pages"]))
    return ", ".join(bits)


def render_entry(r: dict, matchers) -> str:
    authors = format_authors(r["authors"], matchers)
    lines = [f'<li class="cbc-pub">']
    lines.append(f'<span class="cbc-pub-title">{esc(r["title"])}</span>')
    if authors:
        lines.append(f'<span class="cbc-pub-authors">{authors}</span>')
    v = venue(r)
    tail = f'<span class="cbc-pub-venue">{v}' if v else '<span class="cbc-pub-venue">'
    if r["doi"]:
        tail += (f' <a class="cbc-pub-doi" href="https://doi.org/{r["doi"]}">'
                 f'doi.org/{r["doi"]}</a>')
    tail += "</span>"
    lines.append(tail)
    lines.append("</li>")
    return "".join(lines)


def render_list(records, matchers) -> str:
    return ('```{=html}\n<ol class="cbc-pubs">'
            + "".join(render_entry(r, matchers) for r in records)
            + "</ol>\n```\n")


def report_near_duplicates(records) -> None:
    """Warn about titles that are nearly identical but not identical.

    Exact-title deduplication cannot catch a pair like the benzene/Cr(CO)3
    paper, which appears once with "(eta(6)-..." and once with "(?6-..." — the
    normalised forms differ. Fuzzy matching is NOT used to remove entries
    automatically, because two genuinely different papers can share a very
    similar title; they are reported for a human to judge instead.
    """
    seen = [(normalise(r["title"]), r) for r in records if r["title"]]
    pairs = []
    for i, (na, ra) in enumerate(seen):
        for nb, rb in seen[i + 1:]:
            if abs(len(na) - len(nb)) > 12:
                continue
            if difflib.SequenceMatcher(None, na, nb).ratio() >= 0.93:
                pairs.append((ra, rb))
    if pairs:
        warnings.append(f"{len(pairs)} pair(s) of near-identical titles survived "
                        f"deduplication — check whether they are the same paper:")
        for ra, rb in pairs:
            warnings.append(f"    {ra['year']} {ra['title'][:58]}")
            warnings.append(f"    {rb['year']} {rb['title'][:58]}")
            warnings.append("    --")


def touch_dependents(*qmd_names: str) -> None:
    """Bump the mtime of pages that {{< include >}} the generated files.

    Quarto's incremental render does not treat an include as a dependency, so
    after this script rewrites _publications.md the page that includes it is
    considered up to date and keeps its old content — with a NEWER timestamp
    than the file it is stale against, which makes it easy to miss. Touching
    the .qmd makes Quarto re-render it.
    """
    for name in qmd_names:
        path = ROOT / name
        if path.exists():
            path.touch()
            notes.append(f"touched {name} so Quarto re-renders it")


def main() -> None:
    if not CONFIG.exists():
        sys.exit(f"missing {CONFIG.relative_to(ROOT)}")
    cfg = yaml.safe_load(CONFIG.read_text())
    matchers = build_member_matchers(cfg)
    warn_if_preview_running(warnings)

    print("Sources")
    records = load_records(cfg)
    print(f"  {'total':<30} {len(records):>4} entries\n")

    exclude_cfg = cfg.get("exclude") or {}
    excluded_types = {str(x).lower() for x in (exclude_cfg.get("types") or [])}
    title_patterns = [str(x) for x in (exclude_cfg.get("title_patterns") or [])]

    if excluded_types:
        before = len(records)
        records = [r for r in records if r["type"] not in excluded_types]
        notes.append(f"dropped {before - len(records)} entries of excluded type(s): "
                     f"{', '.join(sorted(excluded_types))}")

    def drop(predicate, label):
        nonlocal records
        removed = [r for r in records if predicate(r)]
        records = [r for r in records if not predicate(r)]
        # Reported individually: a careless pattern could otherwise delete real
        # papers without anyone noticing.
        for r in removed:
            notes.append(f"excluded ({label}): {r['year']} {r['title'][:58]}")
        return len(removed)

    if title_patterns:
        rx = re.compile("|".join(re.escape(p) for p in title_patterns), re.I)
        drop(lambda r: bool(rx.search(r["title"])), "non-paper record")

    journal_patterns = [str(x) for x in (exclude_cfg.get("journal_patterns") or [])]
    if journal_patterns:
        jrx = re.compile("|".join(re.escape(p) for p in journal_patterns), re.I)
        drop(lambda r: bool(jrx.search(r["journal"])), "not a journal")

    for entry in (exclude_cfg.get("titles") or []):
        needle = str(entry["match"])
        n = drop(lambda r, needle=needle: needle in r["title"], "named in publications.yml")
        if not n:
            warnings.append(f"exclude.titles entry matched nothing and may be stale: {needle!r}")

    apply_title_fixes(records, cfg)
    flag_corrupt_text(records)

    preprints = dedupe([r for r in records if is_preprint(r)], "preprints")
    publications = dedupe([r for r in records if not is_preprint(r)], "publications")

    unpublished, published_elsewhere = partition_preprints(preprints, publications, cfg)

    def sort_key(r):
        return (r["year"] or "0000", normalise(r["title"]))

    unpublished.sort(key=sort_key, reverse=True)
    publications.sort(key=sort_key, reverse=True)

    # ---- _preprints.md ----
    pre_md = [HEADER]
    if unpublished:
        pre_md.append(render_list(unpublished, matchers))
    else:
        pre_md.append("*No unpublished preprints at present.*\n")
    (ROOT / "_preprints.md").write_text("\n".join(pre_md))

    # ---- _publications.md ----
    # groupby rather than a hand-rolled accumulator: the first version emitted
    # the previous year's heading above each group, duplicating the newest year
    # and losing the oldest.
    out = [HEADER]
    for year, items in groupby(publications, key=lambda r: r["year"] or "Undated"):
        out.append(f"### {year}\n")
        out.append(render_list(list(items), matchers))
    (ROOT / "_publications.md").write_text("\n".join(out))

    touch_dependents("publications.qmd", "research.qmd")

    # ---- summary ----
    print("Result")
    print(f"  unpublished preprints : {len(unpublished)}")
    print(f"  publications          : {len(publications)}")
    if publications:
        years = [r["year"] for r in publications if re.fullmatch(r"\d{4}", r["year"] or "")]
        print(f"  year range            : {min(years)}–{max(years)}")

    report_near_duplicates(publications)

    no_doi = [r for r in publications if not r["doi"]]
    if no_doi:
        warnings.append(f"{len(no_doi)} of {len(publications)} publications have no DOI, so they "
                        f"render without a link. Add DOIs to the .bib to fix.")
    no_journal = [r for r in publications if not r["journal"]]
    if no_journal:
        warnings.append(f"{len(no_journal)} publication(s) have no journal name: "
                        + "; ".join(r["title"][:50] for r in no_journal[:3]))

    if published_elsewhere:
        print(f"\nPreprints excluded because the work is published ({len(published_elsewhere)}):")
        for r, why in sorted(published_elsewhere, key=lambda x: x[0]["year"], reverse=True):
            print(f"  {r['year'] or '????'}  {r['title'][:58]:<58}  [{why}]")

    if notes:
        print("\nNotes:")
        for n in notes:
            print(f"  - {n}")
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ! {w}")
    print("\nWrote _publications.md and _preprints.md.")


if __name__ == "__main__":
    main()
