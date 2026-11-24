"""The phone's browser may be old: the dashboard's scripts must stay plain ES5 (no arrow functions,
let/const, template strings, optional chaining, spread, classes), and every page's files must exist.

    uv run python tests/test_web_assets.py
"""
import pathlib
import re
import sys

WEB = pathlib.Path(__file__).resolve().parent.parent / "deskhub" / "web"
problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


def code_only(src: str) -> str:
    """The script without comments and string contents, so words in text don't count."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            i = src.find("\n", i)
            i = n if i < 0 else i
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(c + c)
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


BAD = {
    "arrow function": r"=>",
    "let/const": r"\b(let|const)\s+[A-Za-z_$\[{]",
    "template string": r"`",
    "optional chaining": r"\?\.[A-Za-z_$\[(]",
    "nullish coalescing": r"\?\?",
    "spread/rest": r"\.\.\.[A-Za-z_$\[(]",
    "class": r"\bclass\s+[A-Za-z_$]",
    "async/await": r"\b(async|await)\b",
}
for js in sorted(WEB.glob("*.js")):
    src = code_only(js.read_text(encoding="utf-8"))
    for name, pat in BAD.items():
        m = re.search(pat, src)
        if m:
            line = src[:m.start()].count("\n") + 1
            check(False, f"{js.name}: {name} near code line {line}")
    # Braces and parentheses must balance (a cheap guard against a half-applied edit).
    for a, b in ("()", "{}", "[]"):
        check(src.count(a) == src.count(b), f"{js.name}: unbalanced {a}{b} ({src.count(a)} vs {src.count(b)})")

# Every file the pages load must exist.
html = (WEB / "index.html").read_text(encoding="utf-8")
for ref in re.findall(r'(?:src|href)="([^"#?:]+)"', html):
    check((WEB / ref).exists() or ref in ("compat", "diag"), f"index.html refers to missing {ref}")
check('<script src="ui.js">' in html and "homeedit.js" in html
      and html.index("ui.js") < html.index("app.js") < html.index("pages.js") < html.index("devices.js") < html.index("homeedit.js") < html.index("DH.start"),
      "scripts must load ui.js, app.js, pages.js, devices.js, homeedit.js, then call DH.start()")
for name in ("compat.html", "diag.html", "app.css", "ui.js", "homeedit.js", "fonts/MaterialIcons-Regular.ttf", "fonts/LICENSE-MaterialIcons.txt"):
    check((WEB / name).exists(), f"missing {name}")

print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
sys.exit(1 if problems else 0)
