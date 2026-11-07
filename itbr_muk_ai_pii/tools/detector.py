# Patterns and check-digit rules ported from pii-tokens (plugin/scripts/pii.py),
# MIT License, Copyright (c) 2026 Lucas Aguilar
# https://github.com/oLucasAguilar/pii-tokens
import re

from .keys import TOKEN_RE

CPF_RE = r'(?<![\w.])\d{3}[. ]?\d{3}[. ]?\d{3}[-. ]?\d{2}(?![\w-])'
CNPJ_RE = r'(?<![\w.])\d{2}[. ]?\d{3}[. ]?\d{3}[/ ]?\d{4}[-. ]?\d{2}(?![\w-])'
PHONE_RE = (
    r'(?<![\w])(?:\+55\s*)?\(\d{2}\)\s?9?\d{4}-?\d{4}(?!\d)'
    r'|(?<![\w])\+55\s*\d{2}\s?9?\d{4}-?\d{4}(?!\d)'
    # no +55 or parentheses: needs a separator, so protocol numbers stay out
    r'|(?P<bare>(?<![\w+])(?:55 )?\d{2} 9?\d{4}[- ]\d{4}(?!\d))'
)
EMAIL_RE = r'(?<![\w.+-])(?P<local>[\w.+-]+)@(?P<domain>[\w-]+(?:\.[\w-]+)+)(?![\w-])'
# One pass, leftmost match wins and the first alternative wins on a tie. Existing
# tokens come first so they are kept; the e-mail comes before CPF/CNPJ so a
# document used as local part does not leak the domain.
DETECT_RE = re.compile(
    rf'(?P<token>{TOKEN_RE.pattern})|(?P<email>{EMAIL_RE})|(?P<cnpj>{CNPJ_RE})'
    rf'|(?P<cpf>{CPF_RE})|(?P<phone>{PHONE_RE})'
)


def _digits(value):
    return re.sub(r'\D', '', value)


def valid_cpf(value):
    d = [int(c) for c in _digits(value)]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for size in (9, 10):
        total = sum(d[i] * (size + 1 - i) for i in range(size))
        if (total * 10) % 11 % 10 != d[size]:
            return False
    return True


def valid_cnpj(value):
    d = [int(c) for c in _digits(value)]
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for size in (12, 13):
        weights = list(range(size - 7, 1, -1)) + list(range(9, 1, -1))
        total = sum(d[i] * weights[i] for i in range(size))
        rest = total % 11
        if (0 if rest < 2 else 11 - rest) != d[size]:
            return False
    return True


# Real Brazilian area codes (DDD).
AREA_CODES = frozenset(
    '11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 41 42 43 44 45 46 47 48 49 '
    '51 53 54 55 61 62 63 64 65 66 67 68 69 71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 '
    '91 92 93 94 95 96 97 98 99'.split()
)
YEAR_RE = re.compile(r'(19|20)\d{2}')


def _phone_value(raw, bare):
    """Return the normalized phone, or None when ``raw`` does not look like one."""
    value = _normalize_phone(raw)
    if value[2:4] not in AREA_CODES:
        return None
    if bare:
        number = value[4:]
        if len(number) == 8 and YEAR_RE.fullmatch(number[:4]) and YEAR_RE.fullmatch(number[4:]):
            return None  # landline shaped like a year range, such as "12 2024-2025"
        if not (len(number) == 9 and number[0] == '9' or len(number) == 8 and number[0] in '2345'):
            return None
    return value


def _normalize_phone(raw):
    digits = _digits(raw)
    if len(digits) in (10, 11):
        digits = '55' + digits
    return digits


def tokenize_text(text, emit, email_domains=frozenset()):
    """Replace CPF, CNPJ, e-mail and phone in ``text`` by ``emit(kind, normalized)``.

    Existing ``TYPE#hex`` tokens are left as they are.
    """
    domains = {d.lower() for d in email_domains}

    def replace(m):
        raw = m.group()
        kind = m.lastgroup
        if kind == 'token':
            return raw
        if kind == 'email':
            if m.group('domain').lower() in domains:
                return raw
            return emit('EMAIL', raw.strip().lower())
        if kind == 'cnpj':
            return emit('CNPJ', _digits(raw)) if valid_cnpj(raw) else raw
        if kind == 'cpf':
            return emit('CPF', _digits(raw)) if valid_cpf(raw) else raw
        phone = _phone_value(raw, m.group('bare'))
        return raw if phone is None else emit('PHONE', phone)

    return DETECT_RE.sub(replace, text)
