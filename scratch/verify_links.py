import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def check_file(md_path: Path):
    content = md_path.read_text(encoding="utf-8")
    # match markdown links [text](path)
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    links = re.findall(pattern, content)
    broken = []
    total = 0
    for text, url in links:
        if url.startswith("http://") or url.startswith("https://") or url.startswith("#"):
            continue
        total += 1
        # resolve relative to md_path.parent
        target = (md_path.parent / url).resolve()
        if not target.exists():
            broken.append((text, url, str(target)))
    return total, broken

all_md = list(ROOT.glob("docs/*.md")) + [ROOT / "README.md"]

total_checked = 0
total_broken = 0

print("=== Link Verification Report ===")
for md in all_md:
    if not md.exists():
        continue
    tot, broken = check_file(md)
    total_checked += tot
    if broken:
        print(f"\n[FAIL] {md.relative_to(ROOT)} has {len(broken)} broken link(s):")
        for text, url, resolved in broken:
            print(f"   [{text}]({url}) -> Resolved to: {resolved} (NOT FOUND)")
        total_broken += len(broken)
    else:
        print(f"[OK] {md.relative_to(ROOT)}: {tot} links verified OK")

print(f"\nTotal local links checked: {total_checked}, Broken: {total_broken}")
if total_broken == 0:
    print("ALL LINKS ARE 100% VALID AND RESOLVE CLEANLY!")

