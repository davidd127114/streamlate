"""Optional profanity masking for VIEWER-FACING output (captions, the
on-stream chat feed). The fear it addresses: speech recognition mishears
something, the translator renders it confidently, and it's burned into the
VOD in a language the streamer can't even read.

Masks common strong profanity in EN/PT/ES out of the box; streamers extend
it via badwords_custom.txt (one word per line) — e.g. paste in a public
list like LDNOOBW for stricter filtering. Output-side only by design.
"""
import os
import re

BUILTIN = [
    # EN
    "fuck", "fucking", "fucker", "motherfucker", "shit", "bullshit",
    "bitch", "bitches", "asshole", "cunt", "dick", "cock", "pussy",
    "whore", "slut", "faggot", "retard", "nigger", "nigga",
    # PT-BR
    "porra", "caralho", "merda", "puta", "putas", "buceta", "cacete",
    "foder", "fodase", "foda-se", "arrombado", "viado", "corno",
    "desgraçado", "filha da puta", "filho da puta", "vagabunda",
    # ES
    "mierda", "puta", "puto", "joder", "coño", "cabrón", "cabron",
    "pendejo", "gilipollas", "polla", "verga", "chinga", "chingada",
    "maricón", "maricon", "zorra",
]

_cache = {"re": None, "mtime": None}


def _custom_path(app_dir):
    return os.path.join(app_dir, "badwords_custom.txt")


def _build(app_dir):
    words = set(BUILTIN)
    path = _custom_path(app_dir)
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                w = line.strip().lower()
                if w and not w.startswith("#"):
                    words.add(w)
    except OSError:
        pass
    pattern = r"(?<!\w)(" + "|".join(
        re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?!\w)"
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


def _regex(app_dir):
    try:
        mtime = os.path.getmtime(_custom_path(app_dir))
    except OSError:
        mtime = 0
    if _cache["re"] is None or _cache["mtime"] != mtime:
        _cache["re"] = _build(app_dir)
        _cache["mtime"] = mtime
    return _cache["re"]


def censor(text, app_dir):
    """Mask matches: first letter + asterisks. 'porra' -> 'p****'."""
    if not text:
        return text

    def mask(m):
        w = m.group(0)
        return w[0] + "*" * (len(w) - 1)

    return _regex(app_dir).sub(mask, text)
