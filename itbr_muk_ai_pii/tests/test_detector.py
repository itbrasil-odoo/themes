import hashlib

from odoo.tests import BaseCase, tagged

from odoo.addons.itbr_muk_ai_pii.tools.detector import tokenize_text


def emit(kind, value):
    return f'{kind}<{value}>'


@tagged('post_install', '-at_install')
class TestDetector(BaseCase):
    def test_cpf_valid_formatted(self):
        self.assertEqual(tokenize_text('CPF 123.456.789-09 ok', emit), 'CPF CPF<12345678909> ok')

    def test_cpf_invalid_digits_kept(self):
        self.assertEqual(tokenize_text('123.456.789-00', emit), '123.456.789-00')

    def test_same_cpf_two_formats(self):
        self.assertEqual(tokenize_text('123.456.789-09', emit), tokenize_text('12345678909', emit))

    def test_cnpj_valid(self):
        self.assertEqual(tokenize_text('11.222.333/0001-81', emit), 'CNPJ<11222333000181>')
        self.assertEqual(tokenize_text('11222333000181', emit), 'CNPJ<11222333000181>')

    def test_email_and_allowed_domain(self):
        self.assertEqual(tokenize_text('A@X.com', emit), 'EMAIL<a@x.com>')
        self.assertEqual(
            tokenize_text('b@empresa.com.br', emit, frozenset({'empresa.com.br'})),
            'b@empresa.com.br',
        )

    def test_phone_parentheses(self):
        self.assertEqual(tokenize_text('(11) 91234-5678', emit), 'PHONE<5511912345678>')

    def test_phone_plus55_spaced(self):
        self.assertEqual(tokenize_text('+55 11 91234-5678', emit), 'PHONE<5511912345678>')

    def test_phone_plus55_bare(self):
        self.assertEqual(tokenize_text('+5511912345678', emit), 'PHONE<5511912345678>')

    def test_phone_plus55_many_spaces(self):
        self.assertEqual(tokenize_text('+55   11 91234-5678', emit), 'PHONE<5511912345678>')

    def test_phone_area_code_separator(self):
        self.assertEqual(tokenize_text('11 91234-5678', emit), 'PHONE<5511912345678>')

    def test_phone_area_code_spaces(self):
        self.assertEqual(tokenize_text('11 91234 5678', emit), 'PHONE<5511912345678>')

    def test_phone_55_prefix_without_plus(self):
        self.assertEqual(tokenize_text('55 11 91234-5678', emit), 'PHONE<5511912345678>')

    def test_phone_landline(self):
        self.assertEqual(tokenize_text('(11) 3456-7890', emit), 'PHONE<551134567890>')

    def test_phone_invalid_area_code_untouched(self):
        self.assertEqual(tokenize_text('20 1234-5678', emit), '20 1234-5678')
        self.assertEqual(tokenize_text('(20) 91234-5678', emit), '(20) 91234-5678')
        self.assertEqual(tokenize_text('+55 10 91234-5678', emit), '+55 10 91234-5678')

    def test_year_ranges_not_phone(self):
        self.assertEqual(tokenize_text('12 2024-2025', emit), '12 2024-2025')
        self.assertEqual(tokenize_text('page 12 2024-2025', emit), 'page 12 2024-2025')
        # Valid DDD and landline shape, but both halves are years: rejected on purpose.
        self.assertEqual(tokenize_text('11 2024-2025', emit), '11 2024-2025')

    def test_mobile_looking_like_years_is_phone(self):
        self.assertEqual(tokenize_text('11 92024-2025', emit), 'PHONE<5511920242025>')
        self.assertEqual(tokenize_text('55 11 92024 2025', emit), 'PHONE<5511920242025>')
        self.assertEqual(tokenize_text('11 92000 1999', emit), 'PHONE<5511920001999>')
        self.assertEqual(tokenize_text('11 91999-2000', emit), 'PHONE<5511919992000>')

    def test_separator_only_number_shape(self):
        self.assertEqual(tokenize_text('11 3456-7890', emit), 'PHONE<551134567890>')
        self.assertEqual(tokenize_text('11 1234-5678', emit), '11 1234-5678')
        self.assertEqual(tokenize_text('11 81234-5678', emit), '11 81234-5678')

    def test_bare_digits_not_phone(self):
        self.assertEqual(tokenize_text('11912345678', emit), '11912345678')
        self.assertEqual(tokenize_text('20240317551', emit), '20240317551')

    def test_existing_token_untouched(self):
        self.assertEqual(tokenize_text('CPF#3f1a9c0d22e4', emit), 'CPF#3f1a9c0d22e4')
        self.assertEqual(tokenize_text('x CPF#123456789098 y', emit), 'x CPF#123456789098 y')

    def test_second_pass_is_noop(self):
        def hex_emit(kind, value):
            return f'{kind}#' + hashlib.sha256(value.encode()).hexdigest()[:12]

        text = 'CPF 123.456.789-09, a@x.com, (11) 91234-5678, 11.222.333/0001-81'
        once = tokenize_text(text, hex_emit)
        self.assertNotEqual(once, text)
        self.assertEqual(tokenize_text(once, hex_emit), once)

    def test_cpf_as_email_local_part(self):
        self.assertEqual(tokenize_text('12345678909@x.com', emit), 'EMAIL<12345678909@x.com>')
        self.assertEqual(tokenize_text('-12345678909@x.com', emit), 'EMAIL<-12345678909@x.com>')

    def test_several_matches_in_one_string(self):
        text = '123.456.789-09 11.222.333/0001-81 a@x.com (11) 91234-5678'
        self.assertEqual(
            tokenize_text(text, emit),
            'CPF<12345678909> CNPJ<11222333000181> EMAIL<a@x.com> PHONE<5511912345678>',
        )

    def test_adjacent_punctuation_and_newlines(self):
        self.assertEqual(tokenize_text('CPF: 123.456.789-09.', emit), 'CPF: CPF<12345678909>.')
        self.assertEqual(tokenize_text('(123.456.789-09)', emit), '(CPF<12345678909>)')
        self.assertEqual(
            tokenize_text('a\n123.456.789-09\nb', emit), 'a\nCPF<12345678909>\nb'
        )

    def test_invalid_cnpj_with_cpf_inside_untouched(self):
        self.assertEqual(tokenize_text('12.345.678/9012-34', emit), '12.345.678/9012-34')
        self.assertEqual(tokenize_text('12345678909012', emit), '12345678909012')

    def test_email_domains_case_insensitive(self):
        self.assertEqual(
            tokenize_text('b@Empresa.COM.br', emit, frozenset({'EMPRESA.com.br'})),
            'b@Empresa.COM.br',
        )

    def test_nul_in_input(self):
        self.assertEqual(tokenize_text('\x00123\x00', emit), '\x00123\x00')
        self.assertEqual(
            tokenize_text('\x000\x00 123.456.789-09', emit), '\x000\x00 CPF<12345678909>'
        )

    def test_protocol_number_not_cpf(self):
        self.assertEqual(tokenize_text('protocolo 20240317551', emit), 'protocolo 20240317551')
