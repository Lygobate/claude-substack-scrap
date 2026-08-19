# claude-substack-scrap

Turn any Substack archive into a folder of clean markdown files, in one command.

A [Claude Code](https://claude.com/claude-code) skill that doubles as a standalone
script. Python 3, standard library only, nothing to install.

```bash
python3 scripts/scrape_substack.py "@handle" --out corpus
```

```
Title       : The Weekly Signal
Publication : https://example.substack.com
Inventory   : 149 sitemap / 122 API -> 149 unique
  1/149 ok     2026-06-04   767 words  What nobody tells you about pricing
  2/149 ok     2026-06-03   852 words  I stopped chasing reach for a month
  3/149 ok     2026-06-02   839 words  The distribution problem, again
  ...
--- 149 written to corpus/ ---
```

A 149-post archive, 85,000 words, in under three minutes. Re-runs are instant: the raw
HTML is cached, so changing format or filter costs nothing.

## What you get

```
corpus/
├── .cache/                                  raw HTML, reused across runs
├── inventory.json                           metadata for every post, bodies excluded
├── 2026-04-15-the-distribution-problem.md
└── ...
```

One file per post, ready to read, grep, or feed to something else:

```markdown
---
title: "The distribution problem, again"
date: 2026-04-15
url: https://example.substack.com/p/the-distribution-problem
slug: the-distribution-problem
words: 783
audience: everyone
---

# The distribution problem, again

If you are reading this, you probably publish somewhere.
...
```

## Install

```bash
git clone https://github.com/Lygobate/claude-substack-scrap.git \
  ~/.claude/skills/substack-scrap
```

The destination directory must be named `substack-scrap`: that name, not the repo's, is
what the skill is invoked by. `~/.claude/skills/` is user-level, so the skill works
across all your projects. To use it as a script only, clone it anywhere.

## Usage

In Claude Code, one line does the whole job — scoping questions, scrape, quality check,
then either the raw corpus or a synthesised playbook:

```
/substack-scrap https://substack.com/@handle
```

As a script:

```bash
# see the scale before committing to anything
python3 scripts/scrape_substack.py "@handle" --list-only

# full archive as markdown
python3 scripts/scrape_substack.py "@handle" --out corpus

# the 30 most recent posts on a given topic
python3 scripts/scrape_substack.py "@handle" --limit 30 --match "growth|acquisition"
```

The target accepts `@handle`, a bare handle, `handle.substack.com`, a custom domain, or
the profile URL exactly as your browser gives it (`substack.com/@handle/posts`).

| Option | Effect |
| --- | --- |
| `--out DIR` | Output directory. Defaults to `./substack-<handle>`. |
| `--limit N` | The N most recent posts. |
| `--match REGEX` | Case-insensitive filter, on the title first, then on the body once fetched. |
| `--format md\|txt` | `md` (default) adds YAML front matter. |
| `--list-only` | Print the inventory without downloading anything. |
| `--refetch` | Bypass the raw HTML cache. |

## It tells you what it missed

Substack injects subscription widgets **inside** the article body, so the obvious regex
stops at the first one and silently truncates the post to its hook. You still get the
right number of files, all looking fine. On a real archive that cost 9 posts out of 34,
one of them a 2,524-byte article reduced to 71 characters.

This scraper ends on real end-of-post markers, then audits its own output and names
anything it could not fully retrieve:

```
/!\ 1 post(s) GATED by Substack — body cut down to the hook, and no option of this
    script gets past it (it needs a logged-in account):
      42 words  https://example.substack.com/p/a-locked-post
    -> treat these as missing from the corpus, not as short.
```

Gated posts also carry `gated: true` in their front matter. Two more checks run
alongside: posts under 133 words get flagged for a manual look, and posts the API marks
subscriber-only are called out as probable teasers.
[`references/pitfalls.md`](references/pitfalls.md) has the full list of traps, including
why `grep paywall` matches every page on the site.

## Requirements

Python 3, no dependencies. PDF export additionally uses headless Chrome, Chromium,
Brave or Edge — whichever it finds.

## Notes

Gated posts need a logged-in account, so they stay out of reach: this scraper does not
authenticate and does not circumvent anything.

The corpus is its author's work. Synthesising a method from it is fair; republishing
their articles reformatted is not.
