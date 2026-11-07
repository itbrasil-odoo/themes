# Patterns and check-digit rules ported from pii-tokens (plugin/scripts/pii.py),
# MIT License, Copyright (c) 2026 Lucas Aguilar
# https://github.com/oLucasAguilar/pii-tokens
import re

from .keys import TOKEN_RE

CPF_RE = re.compile(r'(?<![\w.])\d{3}[. ]?\d{3}[. ]?\d{3}[-. ]?\d{2}(?![\w-])')
CNPJ_RE = re.compile(r'(?<![\w.])\d{2}[. ]?\d{3}[. ]?\d{3}[/ ]?\d{4}[-. ]?\d{2}(?![\w-])')
PHONE_RE = re.compile(
    r'(?<![\w])(?:\+55\s?)?\(\d{2}\)\s?9?\d{4}-?\d{4}(?!\d)'
    r'|(?<![\w])\+55\s?\d{2}\s?9?\d{4}-?\d{4}(?!\d)'
)
EMAIL_RE = re.compile(r'(?<![\w.+-])([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)(?![\w-])', re.IGNORECASE)


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
    # Order matters: CNPJ before CPF (longer first), then e-mail, then phone.
    rules = (
        (CNPJ_RE, lambda m: emit('CNPJ', _digits(m.group())) if valid_cnpj(m.group()) else None),
        (CPF_RE, lambda m: emit('CPF', _digits(m.group())) if valid_cpf(m.group()) else None),
        (EMAIL_RE, lambda m: None if m.group(2).lower() in domains
         else emit('EMAIL', m.group().strip().lower())),
        (PHONE_RE, lambda m: emit('PHONE', _normalize_phone(m.group()))),
    )
    # Split on tokens so nothing inside them is rewritten, and so that the
    # output of an earlier rule is not scanned again by a later one.
    parts = []
    last = 0
    for token in TOKEN_RE.finditer(text):
        parts.append((text[last:token.start()], True))
        parts.append((token.group(), False))
        last = token.end()
    parts.append((text[last:], True))
    out = []
    for chunk, scan in parts:
        if scan:
            chunk = _apply(chunk, rules)
        out.append(chunk)
    return ''.join(out)


def _apply(chunk, rules):
    # Mark replaced spans with placeholders so later rules skip them.
    replaced = []

    def make(fn):
        def sub(m):
            value = fn(m)
            if value is None:
                return m.group()
            replaced.append(value)
            return f'\x00{len(replaced) - 1}\x00'
        return sub

    for regex, fn in rules:
        chunk = regex.sub(make(fn), chunk)
    return re.sub(r'\x00(\d+)\x00', lambda m: replaced[int(m.group(1))], chunk)
