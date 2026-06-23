import pdfplumber
from statistics import median


def split_resume_into_sections(pdf_path, size_ratio=1.05, debug=False):
    
    words = []
    rules = []
    page_offset = 0
    page_width = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            if page_width is None:
                page_width = page.width

            for w in page.extract_words(extra_attrs=["size", "fontname"]):
                fontname = w.get("fontname", "")
                words.append({
                    "text": w["text"],
                    "size": round(w["size"], 1),
                    "top": w["top"] + page_offset,
                    "x0": round(w["x0"], 1),
                    "x1": round(w["x1"], 1),
                    "is_bold": "bold" in fontname.lower(),
                })

            min_len = page.width * 0.5
            for l in page.lines:
                if abs(l["top"] - l["bottom"]) < 1 and (l["x1"] - l["x0"]) >= min_len:
                    rules.append(l["top"] + page_offset)
            for r in page.rects:
                if abs(r["bottom"] - r["top"]) < 2 and (r["x1"] - r["x0"]) >= min_len:
                    rules.append(r["top"] + page_offset)

            page_offset += page.height

            if debug:
                im = page.to_image(resolution=150)
                im.draw_rects(page.extract_words())
                im.save(f"debug_page_{page_num}.png")

    if not words:
        return []

    body_size = median(w["size"] for w in words)
    heading_threshold = body_size * size_ratio
    left_margin = min(w["x0"] for w in words)
    rules.sort()

    has_lines = len(rules) > 0          

    def has_rule_below(line_top, line_bottom, within=12):
        return any(line_bottom - 2 <= r <= line_bottom + within for r in rules)

    words.sort(key=lambda w: (w["top"], w["x0"]))
    lines = []
    current = []
    last_top = None
    for w in words:
        if last_top is None or abs(w["top"] - last_top) <= 3:
            current.append(w)
        else:
            lines.append(current)
            current = [w]
        last_top = w["top"]
    if current:
        lines.append(current)

    sections = []
    current_heading = "HEADER"
    current_lines = []

    BULLETS = {"•", "●", "▪", "‣", "◦", "-", "*", "·", "∗", "○"}

    for line in lines:
        line_text = " ".join(w["text"] for w in line).strip()
        if not line_text:
            continue

        line_x0 = min(w["x0"] for w in line)
        line_x1 = max(w["x1"] for w in line)
        line_top = min(w["top"] for w in line)
        line_bottom = line_top + max(w["size"] for w in line)
        max_size = max(w["size"] for w in line)
        all_bold = all(w["is_bold"] for w in line)

        letters = [c for c in line_text if c.isalpha()]
        is_allcaps = len(letters) >= 2 and all(c.isupper() for c in letters)

        at_left = abs(line_x0 - left_margin) <= 8
        left_gap, right_gap = line_x0, page_width - line_x1
        is_centered = abs(left_gap - right_gap) <= 5 and left_gap > left_margin + 20
        good_position = at_left or is_centered

        is_short = len(line_text.split()) <= 5
        starts_with_bullet = line_text.lstrip()[:1] in BULLETS

        if has_lines:
            is_heading = (
                is_short
                and not starts_with_bullet
                and good_position
                and has_rule_below(line_top, line_bottom)
            )
        else:
            looks_styled = (max_size >= heading_threshold or all_bold or is_allcaps)
            is_heading = (
                is_short
                and not starts_with_bullet
                and good_position
                and looks_styled
            )

        if is_heading:
            sections.append({
                "heading": current_heading,
                "content": "\n".join(current_lines).strip(),
            })
            current_heading = line_text
            current_lines = []
        else:
            current_lines.append(line_text)

    sections.append({
        "heading": current_heading,
        "content": "\n".join(current_lines).strip(),
    })

    return [s for s in sections if s["content"] or s["heading"] != "HEADER"]


if __name__ == "__main__":
    import os, glob

    folder = "../../Training_Data/Resume/"
    pdf_paths = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    print(f"Found {len(pdf_paths)} PDF(s)\n")

    for path in pdf_paths:
        name = os.path.basename(path)
        print(f"\n########## {name} ##########")
        try:
            sections = split_resume_into_sections(path)
            for i, sec in enumerate(sections):
                print(f"\n===== Section {i}: {sec['heading']!r} =====")
                print(sec["content"][:150])
        except Exception as e:
            print(f"✗ FAILED: {e}")