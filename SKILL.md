---
name: substack-scrap
description: >
  Scrape the complete post archive of a Substack author or publication, then either
  hand back the raw corpus as files or synthesise it into a playbook. Use this skill
  whenever the user points at a Substack profile, newsletter, or substack.com URL and
  wants its content pulled down, read in bulk, summarised, turned into a playbook, a
  method, a cheat-sheet, or "everything this person has written" -- even if they never
  say the word "scrape". Also use it when the user names a newsletter author and asks
  what they teach, recommend, or repeat across their posts. It bundles a tested
  stdlib-only scraper plus the specific traps that silently truncate Substack
  articles, so reach for it instead of improvising curl or a markdown reader.
---

# Substack scrap

Pull down every post a Substack author has published, verify nothing got silently
truncated, then deliver either the raw corpus or a synthesised playbook.

The scraping itself is solved: `scripts/scrape_substack.py` handles discovery,
extraction, caching and quality control. Your job is to ask the right questions up
front, run the script, **check its warnings**, and then do the thinking part well.

---

## Step 1 — Ask before scraping

Three decisions change the work materially, and guessing wrong wastes a full scrape.
Ask them together in a single `AskUserQuestion` call, not one at a time:

**Scope.** Everything, or the N most recent posts? Default to everything — a full
archive is usually only 20–200 posts and takes a couple of minutes. Offer a limit
for very large publications or when the user only cares about recent thinking.

**Filter.** All posts, or only a theme? If they want a theme, get keywords from them
and pass `--match` (a case-insensitive regex, e.g. `--match "retargeting|enchère"`).
Worth explaining: filtering happens on the title first, then on the full body after
fetching, because you cannot tell a post's subject from its URL.

**Output.** Two genuinely different deliverables:

- *Raw corpus* — a folder of one file per post. Ask for the format: **markdown
  (default)**, with YAML front matter carrying title/date/url/word count, or plain
  text. Choose this when the user wants to read, grep, or feed the corpus elsewhere.
- *Playbook* — a synthesised document. Ask for the format: **PDF (default)**, HTML
  published as an artifact, or markdown. Choose this when the user wants the method
  rather than the material.

If the user has already stated any of these in their request, don't re-ask it.

---

## Step 2 — Scrape

```bash
python3 scripts/scrape_substack.py "@handle" --out corpus-<handle>
```

Accepts `@handle`, a bare handle, `handle.substack.com`, or a custom domain. Useful
flags: `--limit N`, `--match REGEX`, `--format md|txt`, `--list-only` (inventory
without downloading), `--refetch` (bypass the raw HTML cache).

Raw HTML is cached in `<out>/.cache/`, so re-running to change format or filter costs
nothing. Reach for `--list-only` first when the user wants to see the scale before
committing.

---

## Step 3 — Read the warnings, don't skip this

The script ends with a quality report. It exists because the failure mode here is
silent: you get 34 files, they all look fine, and a quarter of them are three lines
long. Three things to act on:

- **`/!\ N post(s) GATED by Substack`** — the body is a teaser behind an
  unlock wall ("Continuez la lecture", "Réclamer mon post gratuit", sometimes the
  mobile app). No flag gets past it; it needs a logged-in account. Report these as
  missing from the corpus, not as short, and say which posts. Detection keys on the
  `paywall-title` / `paywall-cta` classes only — `unlock`, `subscriber-only` and
  `gate` sit in the JS config of *every* page, free posts included.
- **`/!\ N post(s) suspiciously short`** — open one and compare against the live
  page. Either the post really is short (a webinar announcement, a link round-up), or
  extraction broke on a layout this script hasn't seen. Say which one it is before
  using the corpus.
- **`Note: N post(s) are subscriber-only`** — paywalled posts return a teaser. Your
  synthesis is built on partial material; tell the user which posts and how many.

Also sanity-check the inventory line. It prints sitemap count, API count, and the
union. The sitemap is normally the larger and more complete of the two; if the
sitemap number comes back suspiciously low, the publication may paginate its sitemap
in a way the script didn't follow — check `--list-only` output against the site's
own archive page.

**Read the corpus before synthesising.** Not the titles — the bodies. A playbook
built from headlines inherits the author's marketing framing instead of their method,
and it shows immediately.

---

## Step 4a — Raw corpus output

Write one file per post into the output folder. The script already does this; your
remaining job is to report honestly: how many posts, what date range, total word
count, and anything the quality report flagged. Point the user at `inventory.json`
in the output folder, which carries per-post metadata without the bodies.

---

## Step 4b — Playbook output

A playbook is a synthesis, so structure it by what the reader has to *do*, not by
the order the author published in. What tends to work:

1. The single principle the rest depends on, if the corpus has one.
2. The operational sequence, in application order — and if the order carries real
   information (you can't tune step 4 before step 2 is settled), say so.
3. Thresholds, numbers and benchmarks pulled into a table with `tabular-nums`.
4. Failure modes as a scannable ledger.
5. Whatever the corpus is unusually strong on. Let one section run long.

Then:

- **PDF (default)** — write the HTML, then `scripts/html_to_pdf.sh playbook.html`.
  It uses headless Chrome, because pandoc/weasyprint/wkhtmltopdf are usually absent
  on macOS while Chrome is not. Add `@page { margin: 18mm; }` and avoid
  `position: fixed` so pagination behaves.
- **HTML artifact** — load the `artifact-design` skill first, then publish. Pass the
  file path to `Artifact`.
- **Markdown** — write the file and say where it is.

### Attribution is not optional

The corpus is someone else's work. A playbook is a legitimate synthesis of a method;
a reformatted copy of their articles is not. So: name the author and link the
publication, describe your document as a synthesis, attribute their distinctive
formulations to them rather than adopting them as your own, and mark unverified
figures as the author's own claims rather than established benchmarks. Where the
corpus doubles as sales material for the author's business, say so — it changes how
the reader should weigh it.

---

## Anti AI slop

A corpus synthesis is unusually prone to reading as machine-written, for a reason
specific to this task: **you absorb the author's tics on top of your own.** A
newsletter writer who leans on one word will make you lean on it five times in a
page. Check for that first, then run the general pass.

The governing rule is subtractive — **remove the tells, never add fake humanity.**
Sprinkling in hesitations, forced slang or invented anecdotes produces a second,
cruder artifact.

**Count your repeats.** Before delivering, grep the draft for the words the source
over-uses and for the usual suspects. If a word appears more than twice in a
document, it is a tic:

```bash
for w in levier crucial essentiel véritable incontournable "en effet" "de plus" "par ailleurs"; do
  printf '%-18s %s\n' "$w" "$(grep -oi "$w" draft.html | wc -l | tr -d ' ')"
done
```

**Cut the binary antithesis down to one.** "It isn't a tool problem, it's a method
problem." This is the single most recognisable machine construction, and a corpus of
punchy newsletter posts will hand you a dozen of them. Keep at most one, and only
where the opposition is real. Rewrite the rest as sentences that simply advance.

**Then, in rough order of payoff:**

- Drop hollow openers (`Dans un monde où`, `Force est de constater`, `À l'ère de`)
  and the connectives `En effet`, `De plus`, `Par ailleurs`, `Il convient de noter`.
  Removing a connective almost always leaves the logic intact.
- Test every adjective by swapping it for another from the same family. If the
  sentence still works, the adjective says nothing — cut it or replace it with the
  fact underneath (`crucial` → `ça coûte trois semaines si on le rate`).
- Kill the faux-suspense: `La bonne nouvelle ?`, `Résultat ?`, `Et ce n'est pas
  tout`, `Spoiler :`.
- Break the rule of three. Systematic triads and series of three-item lists are a
  signature; go to two or four, or drop a member. Keep a three when the content
  genuinely has three parts.
- Delete rhetorical questions you immediately answer. Keep the answer.
- Vary sentence length inside each paragraph. A four-word sentence next to a
  thirty-word one is what human rhythm looks like; a page of medium sentences is
  what generated text looks like.
- Make sections deliberately unequal. Six sections of the same length signal that
  nobody cared more about any of them.
- Attribute the author's images and coinages to the author. A cliché you inherited
  from the source is still a cliché, and presenting their invented term as
  established vocabulary is a factual error — `on appelle ça` becomes `ce qu'il
  appelle`.
- State a limit you actually have: what you couldn't verify, what was paywalled,
  where the source is also selling something. This is what makes the rest credible,
  and it is the thing generated text never volunteers.
- No decorative emoji as bullet markers.

If the user has their own `humanize` skill, invoke it for the final pass instead of
re-deriving this — it is more complete, and it is their voice.

---

## Reference

`references/pitfalls.md` — why the scraper is built the way it is, and what breaks
when you simplify it. Seven traps, all of which fail silently: a naive body regex
truncates articles to their hook, the profile page has no post links, `grep paywall`
matches every page including free ones, re-sorting the inventory on API dates makes
`--limit` skip recent posts, a substring boilerplate filter deletes real sentences,
exact-matching the body's CSS class fails every post at once, and a markdown reader
flattens the page beyond use.

It is not a checklist — the script already does all of this. Read it when the scraper
misbehaves, or when porting it to another publishing platform.
