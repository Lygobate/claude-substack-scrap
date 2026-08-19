# Substack: the false routes

**This file is not a checklist.** `scrape_substack.py` already handles everything
below. It exists because several of its choices look needlessly convoluted, and
"simplifying" them re-introduces bugs that fail silently — you still get the right
number of files, and they still look fine.

Read it when the scraper misbehaves, or when porting it to another publishing
platform. Each entry gives the obvious approach, why it fails, and what the code does
instead.

---

## 1. The profile page has no post links

`substack.com/@handle` is a **profile**, not a publication. Its post list is rendered
in JavaScript: the raw HTML contains no `/p/` links at all. Searching for article links
returns zero and makes it look like the handle is wrong.

What the page does contain is a large JSON blob escaped for JS, with backslashes before
the quotes. The publication sits in it like this:

```
\"name\":\"Newsletter title\",\"subdomain\":\"handle\",\"custom_domain\":null
```

So replace `\"` with `"` before any regex, then read `subdomain` and `custom_domain`.
A non-null `custom_domain` wins over the subdomain.

**Trap inside the trap.** That blob also lists publications the author merely *follows*
or recommends. Their position in the list proves nothing. The reliable signal is a
subdomain equal to the handle; failing that, say so out loud instead of silently taking
the first.

**Second trap.** Only the bare profile embeds that blob. `substack.com/@handle/posts` —
the URL a browser hands you when you copy from the address bar — returns a page with
**zero** matches, and the subdomain-counting fallback finds zero candidates too, so
resolution dies with "no publication found" on a perfectly valid handle. Trim the URL
to the handle before fetching. That trailing path would otherwise end up inside the
handle and break the ownership check as well.

---

## 2. The sitemap is more complete than the archive API

Two inventories exist, and they disagree.

| Source | Completeness | What it gives you |
|---|---|---|
| `/sitemap.xml` | The complete one | Every post URL, ordered newest-first |
| `/api/v1/archive?sort=new&limit=50&offset=N` | Partial | `post_date`, `title`, `audience`, `subtitle` |

Measured on two real publications: 34 sitemap / 23 API, and 149 sitemap / 122 API.
Trusting the API alone loses a fifth to a third of the corpus with no error of any kind.

Take the union, sitemap as the reference, API for metadata. The API stays indispensable
for one reason: it is the only place that exposes `audience`, so the only way to know
*in advance* that a post is paywalled.

**Do not re-sort the merged list on API dates.** It is tempting, because "the 10 most
recent" needs an ordering — but every post the API never listed gets an empty date,
which sorts to the bottom. On the 149-post case that made `--limit 30` return 7 wrong
posts out of 30, and not one of the 27 uncatalogued posts, even though all 27 fell
inside the requested window. The sitemap is already strictly newest-first (verified:
zero inversions across 149 posts), so preserving its order is simpler and correct.
Date-sort only as a fallback, when there is no sitemap at all.

On large publications `/sitemap.xml` may be an **index** of sitemaps
(`sitemap/2024.xml`, …). Follow the recursion or you only get the first slice.

---

## 3. Paywall detection: three false positives and two real signals

The word `paywall` appears in the HTML of **every** page, fully free posts included: it
is JS configuration. So do `unlock`, `subscriber-only` and `gate` — all three were
found in all 149 pages of a corpus whose posts were almost entirely free. Concluding
"paywalled" on that basis makes you abandon a perfectly accessible archive.

`only_paid` in the raw HTML is no better. It showed up in 9 files of that corpus, and 8
of them extracted 460–750 words with no problem: the string comes from the JSON of
*recommended* posts, not the current one.

Two signals do work, and they cover different cases.

**`audience` from the archive API.** `everyone` means free; anything else means the body
you get is probably a teaser. Its limit is coverage — posts absent from the API have no
`audience` at all, 27 of 149 in the measured case, so it cannot be the only check.

**`class="paywall-title"` or `class="paywall-cta"` in the page.** Present on exactly 1
file of 149, precisely the gated one. This is the wall itself: a heading along the lines
of "Continuez la lecture de ce post gratuitement" plus a claim button, sometimes
demanding the mobile app. It catches gated posts the API says nothing about.

A gated post is not a short post. Report it as missing from the corpus, or a synthesis
ends up built on an article's hook.

---

## 4. The main trap: widgets injected into the body

The article body is server-rendered inside:

```html
<div dir="auto" class="body markup"> ... </div>
```

The natural reflex is a non-greedy regex ending at the first thing that looks like the
end of the content — typically a subscription widget. **That is wrong.**

Substack injects subscription widgets **in the middle** of the body, often right after
the first two or three paragraphs. A regex stopping at `subscription-widget` therefore
truncates the article to its hook.

Observed symptom: of 34 posts, 9 came back at 31–219 characters, all cut off cleanly
after the opening lines. A 2,524-byte post shrank to 71. And nothing fails — you get
your 34 files.

**What works.** End on markers of a real post ending, never on widgets:

```
class="post-ufi        id="discussion         class="comments-page
data-component-name="PostFooter                class="post-footer
data-component-name="CommentsPage              class="modal-container
```

Take whichever sits closest after the start of the body.

**The guardrail that caught all of this**: after extraction, print the distribution of
body lengths and flag anything abnormally short. It was that check, not the regex, that
exposed the bug. A scraper without a length check is a scraper that lies quietly.

---

## 5. Boilerplate filters delete real sentences

Stripping tags leaves widget chrome behind as plain lines — "Thanks for reading",
"Rédigez votre e-mail", "Partager". Dropping any line that contains one of those
strings looks obvious, and leaks content silently.

Some of those labels are ordinary words. `"partager"` matched as a substring deleted 46
real content lines across 149 posts — sentences of the form *"je voulais partager avec
toi une idée simple"*, plain prose treated as a button label. 952 words vanished, and no
warning fired, because the posts were still a normal length.

Split the list in two. Phrases distinctive enough never to occur in prose ("thanks for
reading", "give a gift subscription") are safe as substrings. Labels that double as
everyday words (partager, s'abonner, commenter, like, subscribe) only count when the
label **is** the whole line.

---

## 6. Exact-string matching on a CSS class fails all at once

`page.find('class="body markup"')` works, until Substack adds a class or reorders an
attribute — at which point every post in the archive fails together with "body not
found". On a tool whose whole point is reporting what it missed, that is a poor way to
fail.

Match the class list instead: `class="[^"]*\bbody\b[^"]*\bmarkup\b[^"]*"`.

---

## 7. A markdown reader is the wrong tool

Jina Reader (`curl https://r.jina.ai/URL`) and equivalent HTML→markdown converters work
well for reading **one** page. They are unfit here for a structural reason: they flatten
the whole page into a single stream of text. The article body, the mid-article
subscription widget, the share bar and the closing CTAs all arrive mixed together, with
no marker to tell them apart.

What you want is not the page. It is the article body, alone, across dozens of files,
with the date and URL in a header so sources stay citable. That takes structural
extraction, hence access to the HTML.

RSS is not an alternative either: Substack truncates it.

---

## Two constraints worth knowing

**The raw HTML is cached** because extraction is the part that gets fixed. Being able to
change format, change filter, or repair a parsing bug and replay instantly — no network,
no extra load on the publication — is what made those 46 deleted lines recoverable after
the fact.

**Requests are spaced ~0.6 s apart.** No throttling observed at that rate across several
hundred posts.
