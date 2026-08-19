#!/usr/bin/env python3
"""
Scrape every post of a Substack publication. Pure stdlib: no pip install needed.

    python3 scrape_substack.py <url-or-handle> [options]

    <url-or-handle>   substack.com/@handle, handle.substack.com, a custom domain,
                      or just the bare handle.

    --out DIR         output directory (default: ./substack-<handle>)
    --limit N         keep only the N most recent posts (default: all)
    --match REGEX     keep only posts whose title or body matches (case-insensitive)
    --format md|txt   output format (default: md, with YAML front matter)
    --refetch         ignore the raw HTML cache and re-download
    --list-only       discover and print the post inventory, write nothing

Exit code is 1 if any post failed to extract, so a caller can react.
"""
import argparse, html, json, os, re, sys, time, urllib.error, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; substack-scrap/1.0)"}
SLEEP = 0.6           # be polite; Substack tolerates this fine
SHORT = 800           # bodies under this are suspicious -> QA flag

# The article body ends at whichever of these appears first. Deliberately does NOT
# include subscription widgets: those are injected *inside* the body, and stopping
# at one truncates the article. See references/pitfalls.md.
END_MARKERS = [
    'class="post-ufi', 'id="discussion', 'class="comments-page',
    'data-component-name="PostFooter', 'class="post-footer',
    'data-component-name="CommentsPage', 'class="modal-container',
]

# Widget chrome that survives tag-stripping, matched case-insensitively per line.
# Phrases distinctive enough that they never occur in prose -> safe as a substring.
BOILERPLATE = [
    "thanks for reading", "subscribe for free", "type your email",
    "share this post", "leave a comment", "discussion about this post",
    "invite your friends", "give a gift subscription",
    "rédigez votre e-mail", "laisser un commentaire", "un abonnement payant",
]

# Button labels that are also ordinary words ("je veux te partager quelque chose").
# These only count when the label IS the whole line: matching them as substrings
# silently deleted 46 real content lines across a 149-post corpus.
BOILERPLATE_EXACT = {
    "partager", "share", "restack", "commenter", "comment", "like", "j'aime",
    "s'abonner", "s\u2019abonner", "abonnez-vous", "subscribe", "voir les réponses",
}


def get(url, timeout=45):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout
    ).read().decode("utf-8", "replace")


def resolve_host(raw):
    """Turn any author reference into the publication's base URL.

    substack.com/@handle is a *profile*, not the publication, and its post list
    is rendered client-side -- there are no /p/ links in the HTML to scrape. The
    publication lives in a backslash-escaped JSON blob embedded in the page,
    which also tells you whether it sits on a custom domain. Read it from there.
    """
    raw = raw.strip().rstrip("/")
    if not raw.startswith("http"):
        raw = ("https://substack.com/@" + raw.lstrip("@")
               if "." not in raw else "https://" + raw)
    if "substack.com/@" not in raw:
        return raw

    # substack.com/@handle/posts is what a browser hands you, but only the bare
    # profile embeds the publication JSON -- and the trailing path would end up
    # inside the handle below. Trim to the handle.
    m = re.match(r"(https://substack\.com/@[^/]+)", raw)
    if m:
        raw = m.group(1)

    try:
        page = get(raw)
    except urllib.error.HTTPError as e:
        sys.exit(f"Cannot read profile {raw}: HTTP {e.code}")

    flat = page.replace('\\"', '"')          # the blob is escaped for JS
    pubs = re.findall(
        r'"name":"([^"]{1,120})","subdomain":"([a-z0-9-]+)","custom_domain":(null|"[^"]+")',
        flat)
    if not pubs:
        subs = [h for h in re.findall(r"https://([a-z0-9-]+)\.substack\.com", page)
                if h not in ("support", "www", "on", "careers", "about")]
        if not subs:
            sys.exit(f"No publication found on {raw}. Check the handle, or pass "
                     f"the publication URL directly (e.g. handle.substack.com).")
        return "https://" + max(set(subs), key=subs.count) + ".substack.com"

    # The blob also lists publications this author merely follows or recommends,
    # so position in the list proves nothing. A subdomain equal to the handle is
    # a strong ownership signal; fall back to first-listed and say so out loud.
    handle = raw.rsplit("@", 1)[1].lower()
    pubs.sort(key=lambda t: t[1].lower() != handle)

    def unesc(t):
        return re.sub(r"\\u([0-9a-fA-F]{4})",
                      lambda m: chr(int(m.group(1), 16)), t)

    if len(pubs) > 1 and pubs[0][1].lower() != handle:
        print("Several publications on this profile, none matching the handle:",
              file=sys.stderr)
        for n, sd, cd in pubs[:8]:
            print(f"    {unesc(n)}  ->  {sd}.substack.com", file=sys.stderr)
        print("Using the first one. Pass the publication URL directly if that "
              "is not the right one.", file=sys.stderr)

    name, sub, custom = pubs[0]
    name = unesc(name)
    print(f"Title       : {name}", file=sys.stderr)
    if custom != "null":
        return "https://" + custom.strip('"')
    return f"https://{sub}.substack.com"


def from_sitemap(base):
    """Sitemap is the most complete inventory. Follow a sitemap index if present."""
    urls, seen = [], set()

    def pull(u):
        try:
            xml = get(u)
        except Exception:
            return
        locs = re.findall(r"<loc>([^<]+)</loc>", xml)
        nested = [l for l in locs if re.search(r"sitemap.*\.xml$", l)]
        if nested:
            for n in nested:
                if n not in seen:
                    seen.add(n)
                    pull(n)
        for l in locs:
            if "/p/" in l and l not in seen:
                seen.add(l)
                urls.append(l.rstrip("/"))

    pull(base + "/sitemap.xml")
    return urls


def from_archive_api(base):
    """Archive API is usually *less* complete than the sitemap, but it carries
    metadata the HTML makes you work for: post_date, title, and `audience`
    (which tells you up front whether a post is paywalled)."""
    meta, offset = {}, 0
    while offset < 2000:
        try:
            batch = json.loads(
                get(f"{base}/api/v1/archive?sort=new&limit=50&offset={offset}")
            )
        except Exception:
            break
        if not batch:
            break
        for p in batch:
            u = (p.get("canonical_url") or "").rstrip("/")
            if u:
                meta[u] = {
                    "date": (p.get("post_date") or "")[:10],
                    "title": p.get("title") or "",
                    "audience": p.get("audience") or "",
                    "subtitle": p.get("subtitle") or "",
                }
        offset += 50
        time.sleep(0.2)
    return meta


def clean(fragment):
    fragment = re.sub(r"<(script|style|form|noscript)\b.*?</\1>", " ",
                      fragment, flags=re.S | re.I)
    fragment = re.sub(r"<li\b[^>]*>", "\n- ", fragment, flags=re.I)
    fragment = re.sub(r"<h([1-6])\b[^>]*>", r"\n\n### ", fragment, flags=re.I)
    fragment = re.sub(r"<(?:p|div|blockquote|tr|section)\b[^>]*>", "\n",
                      fragment, flags=re.I)
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = html.unescape(fragment)
    fragment = re.sub(r"[ \t ]+", " ", fragment)

    keep = []
    for line in fragment.split("\n"):
        line = line.strip()
        if len(line) < 2:
            continue
        low = line.lower()
        if any(b in low for b in BOILERPLATE):
            continue
        if low.strip(" .:!?·|—–-\u00a0") in BOILERPLATE_EXACT:
            continue
        keep.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


def extract(page, url, meta):
    # Match the class list, not the literal string: an extra class or a reordered
    # attribute would otherwise make every single post fail at once.
    k = re.search(r'class="[^"]*\bbody\b[^"]*\bmarkup\b[^"]*"', page)
    if not k:
        return None
    start = page.index(">", k.end()) + 1
    ends = [page.find(m, start) for m in END_MARKERS]
    ends = [e for e in ends if e > start]
    body = clean(page[start:min(ends) if ends else min(start + 150000, len(page))])

    m = re.search(r'<h1[^>]*class="post-title[^"]*"[^>]*>(.*?)</h1>', page, re.S)
    title = clean(m.group(1)).replace("\n", " ") if m else meta.get("title", "")
    d = (re.search(r'"post_date":"([^"]+)"', page)
         or re.search(r'<time[^>]*datetime="([^"]+)"', page))
    date = d.group(1)[:10] if d else meta.get("date", "")
    s = re.search(r'class="subtitle"[^>]*>(.*?)</h3>', page, re.S)
    subtitle = clean(s.group(1)).replace("\n", " ") if s else meta.get("subtitle", "")

    # A gated post returns a teaser plus a wall ("Continuez la lecture...",
    # "Reclamer mon post gratuit"). Only these two classes are reliable: the words
    # unlock / subscriber-only / gate sit in the JS config of *every* page.
    gated = 'class="paywall-title' in page or 'class="paywall-cta' in page

    return {"title": title or "(untitled)", "date": date, "subtitle": subtitle,
            "url": url, "body": body, "words": len(body.split()),
            "audience": meta.get("audience", ""), "gated": gated}


def write(post, outdir, fmt):
    slug = post["url"].rstrip("/").split("/")[-1]
    path = os.path.join(outdir, f"{post['date'] or '0000-00-00'}-{slug}.{fmt}")
    if fmt == "md":
        fm = ["---",
              f"title: {json.dumps(post['title'], ensure_ascii=False)}",
              f"date: {post['date']}",
              f"url: {post['url']}",
              f"slug: {slug}",
              f"words: {post['words']}"]
        if post["subtitle"]:
            fm.append(f"subtitle: {json.dumps(post['subtitle'], ensure_ascii=False)}")
        if post["audience"]:
            fm.append(f"audience: {post['audience']}")
        if post.get("gated"):
            fm.append("gated: true   # body truncated by a Substack wall")
        fm.append("---")
        text = "\n".join(fm) + f"\n\n# {post['title']}\n\n{post['body']}\n"
    else:
        text = (f"{post['title']}\nDATE: {post['date']}\nURL: {post['url']}\n\n"
                f"{post['body']}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--match")
    ap.add_argument("--format", choices=["md", "txt"], default="md")
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--list-only", action="store_true")
    a = ap.parse_args()

    base = resolve_host(a.target)
    handle = base.split("//")[1].split(".")[0]
    print(f"Publication : {base}", file=sys.stderr)

    sm = from_sitemap(base)
    api = from_archive_api(base)
    urls = sm or sorted(api, reverse=True)
    extra = [u for u in api if u not in set(urls)]
    urls += extra
    print(f"Inventory   : {len(sm)} sitemap / {len(api)} API "
          f"-> {len(urls)} unique", file=sys.stderr)

    # The sitemap is already newest-first AND is the only complete inventory.
    # Re-sorting on API dates gives every post the API never listed an empty key,
    # which sinks it to the bottom -- so --limit N would silently skip recent
    # posts. Trust sitemap order; date-sort only if there was no sitemap at all.
    if not sm:
        urls.sort(key=lambda u: api.get(u, {}).get("date", ""), reverse=True)

    if a.match:
        rx = re.compile(a.match, re.I)
        pre = [u for u in urls
               if rx.search(api.get(u, {}).get("title", "")) or u not in api]
        print(f"Pre-filter  : {len(pre)}/{len(urls)} kept on title "
              f"(uncatalogued posts pass through, filtered on body later)",
              file=sys.stderr)
        urls = pre
    if a.limit:
        urls = urls[:a.limit]

    if a.list_only:
        for u in urls:
            m = api.get(u, {})
            print(f"{m.get('date','?'):10}  {m.get('audience','?'):8}  {u}")
        return 0

    outdir = a.out or f"substack-{handle}"
    cache = os.path.join(outdir, ".cache")
    os.makedirs(cache, exist_ok=True)

    rx = re.compile(a.match, re.I) if a.match else None
    ok, failed, short, skipped, gated = [], [], [], [], []

    for i, u in enumerate(urls, 1):
        slug = u.rstrip("/").split("/")[-1]
        raw = os.path.join(cache, slug + ".html")
        if os.path.exists(raw) and not a.refetch and os.path.getsize(raw) > 5000:
            page = open(raw, encoding="utf-8", errors="replace").read()
        else:
            try:
                page = get(u)
            except Exception as e:
                failed.append((slug, str(e)))
                print(f"{i:>3}/{len(urls)} FAILED {slug} — {e}", file=sys.stderr)
                continue
            open(raw, "w", encoding="utf-8").write(page)
            time.sleep(SLEEP)

        post = extract(page, u, api.get(u, {}))
        if not post or not post["body"]:
            failed.append((slug, "body not found"))
            print(f"{i:>3}/{len(urls)} EMPTY  {slug}", file=sys.stderr)
            continue
        if rx and not (rx.search(post["title"]) or rx.search(post["body"])):
            skipped.append(slug)
            continue

        write(post, outdir, a.format)
        ok.append(post)
        if post.get("gated"):
            gated.append(post)
        flag = ("  <-- GATED" if post.get("gated")
                else "  <-- SHORT" if post["words"] * 6 < SHORT else "")
        if flag == "  <-- SHORT":
            short.append(post)
        print(f"{i:>3}/{len(urls)} ok     {post['date']} {post['words']:>5} words  "
              f"{post['title'][:48]}{flag}", file=sys.stderr)

    print(f"\n--- {len(ok)} written to {outdir}/ ---", file=sys.stderr)
    if skipped:
        print(f"{len(skipped)} off-topic (--match)", file=sys.stderr)
    if gated:
        print(f"\n/!\\ {len(gated)} post(s) GATED by Substack — body cut down to "
              f"the hook, and no option of this script gets past it (it needs a "
              f"logged-in account, sometimes the Substack app):", file=sys.stderr)
        for p in gated:
            print(f"    {p['words']:>4} words  {p['url']}", file=sys.stderr)
        print("    -> treat these as missing from the corpus, not as short.",
              file=sys.stderr)
    if short:
        print(f"\n/!\\ {len(short)} post(s) suspiciously short — check one by "
              f"hand against the live page before using the corpus:",
              file=sys.stderr)
        for p in short:
            print(f"    {p['words']:>4} words  {p['url']}", file=sys.stderr)
    if failed:
        print(f"\n/!\\ {len(failed)} failure(s):", file=sys.stderr)
        for s, e in failed:
            print(f"    {s}: {e}", file=sys.stderr)

    paid = [p for p in ok if p["audience"] not in ("", "everyone")]
    if paid:
        print(f"\nNote: {len(paid)} post(s) are subscriber-only — the body you "
              f"got is probably a teaser.", file=sys.stderr)

    with open(os.path.join(outdir, "inventory.json"), "w", encoding="utf-8") as f:
        json.dump({"publication": base, "written": len(ok),
                   "posts": [{k: v for k, v in p.items() if k != "body"}
                             for p in ok]}, f, ensure_ascii=False, indent=2)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
