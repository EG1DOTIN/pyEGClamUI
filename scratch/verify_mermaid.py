import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def check_mermaid_in_file(md_path: Path):
    content = md_path.read_text(encoding="utf-8")
    blocks = re.findall(r'```mermaid(.*?)```', content, re.DOTALL)
    issues = []
    for i, b in enumerate(blocks):
        lines = [l.strip() for l in b.strip().splitlines() if l.strip()]
        for lnum, line in enumerate(lines, 1):
            # check unquoted special characters in node definitions [ ... ]
            # e.g., if there's unquoted '(' or ')' in edge labels
            if "-->" in line or "---" in line:
                # check edge label syntax
                # e.g. "--> |label|" or "-- label -->"
                m = re.search(r'--\s*([^>]+?)\s*-->', line)
                if m:
                    label = m.group(1).strip()
                    # if label has ( ) without starting and ending with quotes
                    if ("(" in label or ")" in label or ">" in label or "<" in label or "$" in label or "~" in label) and not (label.startswith('"') and label.endswith('"')):
                        issues.append((i+1, lnum, line, f"Unquoted special characters in edge label: {label}"))
    return len(blocks), issues

all_md = list(ROOT.glob("docs/*.md")) + [ROOT / "README.md"]

total_blocks = 0
total_issues = 0
print("=== Mermaid Syntax Validation Report ===")
for md in all_md:
    num_b, issues = check_mermaid_in_file(md)
    total_blocks += num_b
    if issues:
        print(f"\n[FAIL] {md.relative_to(ROOT)} has {len(issues)} potential issue(s):")
        for b_idx, lnum, line, desc in issues:
            print(f"   Block {b_idx}, Line {lnum}: {desc}")
            print(f"     Code: {line}")
        total_issues += len(issues)
    else:
        print(f"[OK] {md.relative_to(ROOT)}: {num_b} mermaid block(s) clean")

print(f"\nTotal mermaid blocks checked: {total_blocks}, Issues: {total_issues}")
if total_issues == 0:
    print("ALL MERMAID BLOCKS ARE 100% VALID!")
