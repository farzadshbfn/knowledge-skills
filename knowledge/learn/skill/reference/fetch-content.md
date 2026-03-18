# Web Content Fetching and Caching

How to fetch and cache web content (articles, docs) for the kb-learn skill, minimizing tokens and noise.

## Contents
- [Workflow](#workflow)
- [Tool Priority](#tool-priority)
- [Cache Management](#cache-management)
- [Error Handling](#error-handling)

## Workflow

1. **Setup cache**: `mkdir -p /tmp/learning-kb-cache/$(date +%Y-%m-%d)`
2. **Generate slug**: `CACHE_SLUG=$(echo "$URL" | sed 's|https\?://||' | sed 's|/$||' | tr '/' '-' | tr '?' '-' | cut -c 1-80)`
3. **Check cache**: If `$CACHE_DIR/${CACHE_SLUG}.md` exists, use it
4. **Extract content** using the first available tool (see priority below)
5. **Verify**: If output file is empty, remove it and try the next tool or ask user to paste text
6. **Process**: Read cached file for claim extraction

## Tool Priority

Use the first available tool:

1. **reader** (Mozilla Readability) — best for most articles. `reader "$URL" > "$CACHE_FILE"`
2. **trafilatura** — best for blogs/news. `trafilatura --URL "$URL" --output-format txt --no-comments > "$CACHE_FILE"`
3. **WebFetch** — fallback when extraction tools unavailable

Check availability: `command -v reader` or `command -v trafilatura`. Inform user which tool is used; suggest `npm install -g reader-cli` if using fallback.

## Cache Management

- Cache location: `/tmp/learning-kb-cache/YYYY-MM-DD/`
- Reuse cache for same URL in same session
- Skip cache when user says "fetch fresh" or URL params changed
- OS manages `/tmp/` cleanup automatically

## Error Handling

| Failure | Action |
|---------|--------|
| Network error / timeout | Ask user to paste article text |
| Paywall / auth required | Ask user to paste text (tools cannot bypass) |
| Empty extraction | Try next tool in priority; if all fail, ask for pasted text |
| Invalid URL | Ask user for valid URL or pasted content |
