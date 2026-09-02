# CompBioCat website — project memory

The public website for the CompBioCat research group (IQCC, Universitat de Girona),
co-led by Marc Garcia-Borràs and Ferran Feixas. Deployed at https://compbiocat.github.io
from the `compbiocat` GitHub organization.

Read `content/BRIEF.md` for all site content and the tab-by-tab specification.
Read this file for how to build and what not to do.

---

## Stack

- **Quarto** (static site generator). Same toolchain as https://ferranfeixas.github.io
  so the two sites stay maintainable by the same people.
- Custom SCSS theme. No Bootstrap theme swaps, no CSS frameworks.
- Fonts: **Inter** only, via Google Fonts. Weights 400 and 500. Never 600/700.
- Python for the small content-generation scripts (see below). No Node build step.
- Output to `_site/`, deployed by GitHub Actions to the `gh-pages` branch.

## Repo layout

```
_quarto.yml              site config, navbar, theme
index.qmd                home
news.qmd                 news listing (all items)
research.qmd
publications.qmd         includes generated _publications.md
team.qmd                 includes generated _team.md
projects.qmd             includes generated _projects.md
code-and-data.qmd        "Repositories and data"
contact.qmd
news/                    one .qmd per news item: YYYY-MM-DD-slug.qmd
data/publications.bib    BibTeX exported from both ORCIDs (source of truth)
data/team.yml
data/projects.yml
scripts/build_publications.py
scripts/build_team.py
scripts/build_projects.py
assets/scss/custom.scss
assets/images/{banner,people,logos}/
.nojekyll
```

## Content-generation pattern

The group updates content often and neither PI should have to touch layout code.
So: **content lives in data files, never inside .qmd layouts.**

- **News** uses Quarto's native listing feature. Adding news = adding one file to
  `news/`. Front matter: `title`, `date`, optional `image`, optional `categories`.
  `news.qmd` lists all; the home page lists the 6 most recent.
- **Publications** come from `data/publications.bib`. `scripts/build_publications.py`
  parses it, deduplicates (by DOI, falling back to normalized title), sorts newest
  first, groups under year headings, bolds group-member author names, and writes
  `_publications.md`. Re-run after updating the .bib.
- **Team** and **Projects** work the same way from their YAML files.

Generated `_*.md` files are committed so the site builds without Python on CI.
Every generated file starts with a comment saying which script produced it and
that hand edits will be overwritten.

**Never run `quarto render` while `quarto preview` is running.** They write to
the same `_site/` and `.quarto/`. The preview can re-render a page from its own
cached view and overwrite correct output — five excluded records reappeared on
the publications page this way, *after* being verified as gone, because the
generated `.md` was right and the HTML was one build behind. The build scripts
now warn when a preview is running. Stop it, render, restart it.

**Quarto does not treat `{{< include >}}` as a dependency for incremental
renders.** After a build script rewrites a generated file, the page including it
is considered up to date and keeps its old content — with a *newer* mtime than
the file it is stale against, which makes it very easy to miss. The build
scripts therefore `touch` the pages that include their output. If you add a new
page that includes a generated file, add it to that list in the script, or use
`quarto render <that-page>.qmd` after building.

## Commands

```bash
quarto preview                  # local dev server, live reload
quarto render                   # full build into _site/
python scripts/build_publications.py
python scripts/build_team.py
python scripts/build_projects.py
```

Always `quarto preview` and actually look at the result before committing. Check
mobile width too — the site must work down to 360px.

## Deployment

GitHub Actions workflow: on push to `main`, render with Quarto and publish to
`gh-pages`. Pages is configured to serve from `gh-pages`. `.nojekyll` must exist
so GitHub doesn't run Jekyll over the output. Do not commit `_site/` to `main`.

---

## Design direction

Pinned by the group. Follow it; don't substitute a different look.

**Concept.** Editorial and quiet. A single column of content on a generous left-aligned
measure, structured by whitespace and hairline rules rather than by cards. The site
should read like a well-set document, not a SaaS landing page. The group's work is
mechanism and precision; the design should feel precise, not promotional.

**Type.** Inter throughout, 400 and 500 only. Sentence case everywhere, including
headings and nav. Body measure under 80 characters. Set a real type scale rather than
ad-hoc sizes. Let size and spacing carry hierarchy, not weight or color.

**Palette.** Five values, all overridable from one place in `custom.scss`:

```scss
$paper:  #FBFBF9;  // page
$ink:    #161918;  // primary text
$muted:  #5A605C;  // secondary text, dates, metadata
$rule:   #E2E4E0;  // hairlines
$accent: #1F6F5C;  // links, sparing emphasis — deep viridian
```

The accent is deliberately a single cool green: it nods to sustainable catalysis
without being a literal green-chemistry cliché, and it is one variable so the group
can change it in seconds. Do not add a second accent.

**Layout.** Full-bleed banner image at the top of the home page only. Everything else
sits on the text measure. Section separation by space first, hairline rules second.
Border radius: 0 or near-0 — but do not chase a broadsheet pastiche.

**Do not use these** (they are generic tells, and the group has explicitly dropped them):
- ALL-CAPS letterspaced eyebrow labels above headings. Use a plain heading, or nothing.
- `01 / 02 / 03` numbering on the research areas — they are parallel, not sequential.
  Numbering is only legitimate where content genuinely is ordered.
- `→` or `↗` appended to link or button text. Write "All news", not "All news →".
- Metadata strung together with middle dots.
- Accenting one word inside a headline in a different color or italic.
- Cards for content that isn't a bounded object. Hairlines and space instead.
- Entrance animations on scroll, hover lifts on every element, gradient washes.

**Motion.** Essentially none. Focus states and link underlines must be visible; respect
`prefers-reduced-motion`.

**Before writing the theme**, read the `frontend-design` skill and do its two-pass
process — draft a compact token/layout plan, critique it against this brief, then build.
The constraints above are fixed; spend your judgement on the type scale, spacing rhythm,
and how the news index and team grid are set.

---

## Guardrails

**Never invent facts.** Do not fabricate paper titles, citation counts, grant numbers,
dates, thesis topics, or people. Everything factual comes from `content/BRIEF.md` or
the .bib file. Where the brief marks something `TODO`, render a visible `TODO` placeholder
in the page and list it in the build summary. Do not guess and do not quietly fill gaps
from general knowledge or web search.

**Never download institutional logos.** UdG, IQCC and ICREA logos have usage rules and
will be supplied by the group as files in `assets/images/logos/`. If they're absent, leave
a correctly-sized empty placeholder box.

**Missing images** get a neutral placeholder at the right aspect ratio, never a stock
photo and never an AI-generated image. The previous version of this site used Unsplash
stock photography; that is exactly what the group is replacing.

**Don't restructure content into layouts.** If a task tempts you to hardcode a team
member or a paper into a .qmd, add it to the YAML/bib and regenerate instead.

**Ask rather than assume** on anything about people's names, titles, or affiliations.
Getting a colleague's name wrong on their own lab site is worse than shipping a day later.

## Working style

Work in phases and stop for review between them: (1) scaffold and theme, (2) home and
news, (3) research and publications, (4) team and projects, (5) code-and-data, contact,
polish. Preview after each. Commit in small labelled commits. Do not push to `main`
without being asked.
