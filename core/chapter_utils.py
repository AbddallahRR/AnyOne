import re


def normalize_chapter_number(num: str) -> str:
    parts = num.split('.')
    parts[0] = parts[0].lstrip('0') or '0'
    return '.'.join(parts)


def chapter_float_key(num: str) -> float:
    try:
        if num.replace('.', '', 1).isdigit():
            return float(num)
    except ValueError:
        pass
    return 0.0


def chapter_to_filename(num: str, padding: int = 4) -> str:
    parts = num.split('.')
    int_part = parts[0].lstrip('0') or '0'
    formatted = f"{int(int_part):0{padding}d}"
    if len(parts) > 1:
        formatted += f"_{parts[1]}"
    return formatted


def parse_chapter_from_filename(name: str) -> str | None:
    m = re.search(r'(\d+(?:_\d+)?)$', name.replace('.mp4', ''))
    if not m:
        return None
    raw = m.group(1).replace('_', '.')
    return normalize_chapter_number(raw)
