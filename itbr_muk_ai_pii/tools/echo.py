"""Mask again, in a tool's output, the values revealed for its arguments.

A tool run with real values may echo them (``open_view`` returns its domain,
an error quotes a value); the output goes to the provider, so each echo is
swapped back for its token.
"""
import json
import re

DIGIT_KINDS = frozenset({'CPF', 'CNPJ', 'PHONE'})
# What may sit between the digits of a formatted document or phone.
SEP = r'[\s.\-/()]*'
DUMP_STYLES = [
    {'indent': indent, 'ensure_ascii': ascii_only}
    for indent in (2, None, 4, 1)
    for ascii_only in (True, False)
]


def _digit_pattern(kind, value):
    digits = re.sub(r'\D', '', value)
    if not digits:
        return None
    prefix = ''
    if kind == 'PHONE':
        if digits.startswith('55') and len(digits) in (12, 13):
            digits = digits[2:]
            prefix = rf'(?:\+?5{SEP}5{SEP})?'
        prefix += r'\(?'
    return re.compile(rf'(?<!\d){prefix}{SEP.join(digits)}(?!\d)')


def _text_pattern(form):
    words = form.split()
    if not words:
        return None
    body = r'\s+'.join(re.escape(word) for word in words)
    return re.compile(rf'(?<!\w){body}(?!\w)', re.IGNORECASE)


def mask_patterns(mask):
    """Return ``(pattern, token)`` pairs for ``{value: token}``, longest value first.

    Documents and phones match in any formatting; other values match as whole
    words, in any case, raw and as JSON escapes them once or twice.
    """
    pairs = []
    for value in sorted(mask, key=len, reverse=True):
        token = mask[value]
        kind = token.partition('#')[0]
        if kind in DIGIT_KINDS and (pattern := _digit_pattern(kind, value)):
            pairs.append((pattern, token))
            continue
        once = json.dumps(value)[1:-1]
        twice = json.dumps(once)[1:-1]
        for form in dict.fromkeys((value, once, twice)):
            if pattern := _text_pattern(form):
                pairs.append((pattern, token))
    return pairs


def mask_text(text, pairs):
    for pattern, token in pairs:
        text = pattern.sub(token, text)
    return text


def mask_tree(data, pairs):
    """Mask the string leaves of ``data``; keys, numbers and booleans stay as they are."""
    if isinstance(data, str):
        return mask_text(data, pairs)
    if isinstance(data, dict):
        return {key: mask_tree(value, pairs) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [mask_tree(value, pairs) for value in data]
    return data


def _dump_like(original, parsed, masked):
    """Serialize ``masked`` the way ``original`` was serialized from ``parsed``."""
    for style in DUMP_STYLES:
        if json.dumps(parsed, **style) == original:
            return json.dumps(masked, **style)
    return json.dumps(masked, indent=2 if '\n' in original else None)


def mask_output(output, pairs):
    """Return a tool ``output`` with its echoes masked.

    JSON text is masked leaf by leaf and serialized the same way again;
    other text is masked as a whole.
    """
    if not pairs:
        return output
    if not isinstance(output, str):
        return mask_tree(output, pairs)
    try:
        parsed = json.loads(output)
    except ValueError:
        return mask_text(output, pairs)
    if not isinstance(parsed, (dict, list, str)):
        return output
    masked = mask_tree(parsed, pairs)
    return output if masked == parsed else _dump_like(output, parsed, masked)
