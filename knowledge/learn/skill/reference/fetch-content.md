# Web Content Fetching and Caching

How to fetch and cache web content (articles, docs) for the kb-learn skill, minimizing tokens and noise.

## Contents
- [Workflow](#workflow)
- [Tool Priority](#tool-priority)
- [Cache Management](#cache-management)
- [Error Handling](#error-handling)

## URL Validation

Before fetching, validate the URL:

1. **Scheme**: Only `https://` and `http://` are allowed. Reject `file://`, `data://`, `javascript:`, and all other schemes.
2. **Format**: Must be a well-formed URL with a valid hostname. Reject bare paths, IPs in private ranges (127.x, 10.x, 192.168.x), and localhost.

If validation fails, tell the user and ask for a valid URL.

## Workflow

1. **Validate URL** per rules above
2. **Setup cache**: `mkdir -p /tmp/learning-kb-cache/$(date +%Y-%m-%d)`
3. **Generate slug**: Strip scheme and trailing slash from the validated source address, replace `/` and `?` with `-`, truncate to 80 chars
4. **Check cache**: If `$CACHE_DIR/${CACHE_SLUG}.md` exists, use it
5. **Extract content** using the first available tool (see priority below)
6. **Verify**: If output file is empty, remove it and try the next tool or ask user to paste text
7. **Process**: Read cached file for claim extraction

## Tool Priority

Use the first available tool:

1. **reader** (Mozilla Readability) — best for most articles. Pass the validated source address to `reader`, redirect output to cache file.
2. **trafilatura** — best for blogs/news. Pass the validated source address via `--URL`, with `--output-format txt --no-comments`, redirect to cache file.
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
