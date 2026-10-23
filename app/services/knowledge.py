"""Shared knowledge base of resolved support cases.

Cases are saved from team notes or solved chats (tidied by the model), checked
for duplicates, and searched with BM25 so relevant ones are added to prompts.
"""
import math
import re
from collections import Counter

from app import db, ollama_client
from app.config import PROMPTS_DIR

FIELDS = ("title", "problem", "cause", "fix", "keywords")
CHUNK_CHARS = 4000  # small chunks so the model doesn't skip cases
MIN_SCORE = 1.0
DUP_SIMILARITY = 0.45  # problems must overlap this much before the model is asked

_FIXED = re.compile(
    r"\b(fixed|resolved|solved|sorted|works now|working now|it worked|that worked|"
    r"all good now|problem gone|issue gone)\b", re.I)
_NOT_FIXED = re.compile(
    r"\b(not|isn'?t|wasn'?t|hasn'?t|didn'?t|doesn'?t|never|still|no longer)\b\W+(\w+\W+){0,2}"
    r"(fixed|resolved|solved|sorted|work)", re.I)
_WORD = re.compile(r"[a-z0-9]+")
# Paragraphs that start a new section (==== lines, # headings, "Issue 3:"...): safe places to split.
_SECTION = re.compile(r"^\s*([=\-_*~#]{3,}|#{1,6}\s|(issue|case|problem)\b)", re.I)
_STOP = set(
    "a an and are as at be but by can do does for from has have how i if in is it its me my "
    "no not of on or our so that the their them then there this to was we what when where "
    "which who why will with you your".split())

_CASE = {"type": "object", "properties": {f: {"type": "string"} for f in FIELDS},
         "required": list(FIELDS)}
_NOTES_SCHEMA = {"type": "object", "properties": {"cases": {"type": "array", "items": _CASE}},
                 "required": ["cases"]}
_CHAT_SCHEMA = {"type": "object",
                "properties": {"resolved": {"type": "boolean"}, **_CASE["properties"]},
                "required": ["resolved", *FIELDS]}
_DUP_SCHEMA = {"type": "object", "properties": {"same_issue": {"type": "boolean"}},
               "required": ["same_issue"]}


def _prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def looks_fixed(text: str) -> bool:
    return bool(_FIXED.search(text)) and not _NOT_FIXED.search(text)


# ---------- search ----------


def _tokens(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower()):
        if w in _STOP:
            continue
        for suffix in ("ing", "ers", "ed", "er", "es", "s", "e"):
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                w = w[: -len(suffix)]
                if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiouls":
                    w = w[:-1]  # scann -> scan, stopp -> stop
                break
        out.append(w)
    return out


def _doc_tokens(case: dict) -> list[str]:
    # Title and keywords count double.
    return _tokens(" ".join([case["title"], case["keywords"]] * 2 + [
        case["problem"], case["cause"], case["fix"]]))


def search(query: str, k: int = 3, min_score: float = MIN_SCORE) -> list[dict]:
    terms = set(_tokens(query))
    cases = db.list_cases()
    if not terms or not cases:
        return []
    docs = [Counter(_doc_tokens(c)) for c in cases]
    avg = sum(sum(d.values()) for d in docs) / len(docs)
    df = Counter(t for d in docs for t in terms if t in d)
    scored = []
    for case, d in zip(cases, docs):
        length = sum(d.values())
        score = 0.0
        for t in terms:
            if t in d:
                idf = math.log(1 + (len(docs) - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * d[t] * 2.2 / (d[t] + 1.2 * (0.25 + 0.75 * length / avg))
        if score >= min_score:
            scored.append((score, case))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [c for _, c in scored[:k]]


def _format(case: dict) -> str:
    text = f"Case: {case['title']}\nProblem: {case['problem']}\n"
    if case["cause"]:
        text += f"Cause: {case['cause']}\n"
    return text + f"Fix: {case['fix']}"


def retrieve(query: str, k: int = 3) -> list[str]:
    return [_format(c) for c in search(query, k)]


# ---------- saving ----------


def _clean(data: dict) -> dict | None:
    case = {f: " ".join(str(data.get(f, "")).split()) if f in ("title", "keywords")
            else str(data.get(f, "")).strip() for f in FIELDS}
    return case if case["title"] and case["problem"] and case["fix"] else None


def _similarity(a: set, b: set, idf: dict) -> float:
    """Weighted overlap of two token sets: 1.0 = same words, 0 = nothing shared."""
    weight = lambda terms: sum(idf[t] for t in terms)
    return weight(a & b) / (min(weight(a), weight(b)) or 1)


async def _find_duplicate(case: dict) -> dict | None:
    # Compare problems by rare words, so shared words like "RetailManager" don't count much.
    cases = db.list_cases()
    if not cases:
        return None
    sets = [set(_tokens(f"{c['title']} {c['problem']}")) for c in cases]
    new = set(_tokens(f"{case['title']} {case['problem']}"))
    df = Counter(t for terms in sets + [new] for t in terms)
    idf = {t: math.log(1 + (len(sets) + 1) / n) for t, n in df.items()}
    score, best = max(((_similarity(new, terms, idf), c) for terms, c in zip(sets, cases)),
                      key=lambda x: x[0])
    if score < DUP_SIMILARITY:
        return None
    data = await ollama_client.complete_json([
        {"role": "system", "content": _prompt("case_duplicate.txt")},
        {"role": "user", "content": f"Existing case:\n\n{_format(best)}\n\nNew case:\n\n{_format(case)}"},
    ], _DUP_SCHEMA)
    return best if data.get("same_issue") is True else None


async def _save(case: dict, source: str, uid: int, cid: int | None = None) -> dict:
    dup = await _find_duplicate(case)
    if dup:
        return {"status": "duplicate", "title": dup["title"]}
    db.add_case(case, source, uid, cid)
    return {"status": "saved", "title": case["title"]}


def _chunks(text: str) -> list[str]:
    """Split long text into pieces, cutting between sections so an issue isn't split in half."""
    paras = []
    for para in re.split(r"\n\s*\n", text):
        if para.strip():
            paras += [para[i:i + CHUNK_CHARS] for i in range(0, len(para), CHUNK_CHARS)]
    chunks, current = [], []
    for para in paras:
        if current and sum(map(len, current)) + len(para) > CHUNK_CHARS:
            starts = [i for i, p in enumerate(current) if i and _SECTION.match(p)]
            cut = starts[-1] if starts else len(current)
            chunks.append("\n\n".join(current[:cut]))
            current = current[cut:]
            if sum(map(len, current)) + len(para) > CHUNK_CHARS:
                chunks.append("\n\n".join(current))
                current = []
        current.append(para)
    return chunks + ["\n\n".join(current)] if current else chunks


async def save_from_text(text: str, uid: int) -> list[dict]:
    results = []
    for chunk in _chunks(text):
        data = await ollama_client.complete_json([
            {"role": "system", "content": _prompt("case_from_notes.txt")},
            {"role": "user", "content": f"Notes:\n\n{chunk}"},
        ], _NOTES_SCHEMA)
        for raw in data.get("cases", []):
            case = _clean(raw)
            if case:
                results.append(await _save(case, "notes", uid))
    return results


async def save_from_chat(cid: int, uid: int) -> dict:
    lines = [f"{'Staff' if m['role'] == 'user' else 'Bobby'}: {m['content']}"
             for m in db.get_messages(cid)]
    transcript = "\n\n".join(lines)[-12000:]
    data = await ollama_client.complete_json([
        {"role": "system", "content": _prompt("case_from_chat.txt")},
        {"role": "user", "content": f"Conversation:\n\n{transcript}"},
    ], _CHAT_SCHEMA)
    case = _clean(data) if data.get("resolved") else None
    if not case:
        return {"status": "skipped"}
    existing = db.get_case_by_conversation(cid)
    if existing:
        db.update_case(existing["id"], case)
        return {"status": "updated", "title": case["title"]}
    return await _save(case, "chat", uid, cid)