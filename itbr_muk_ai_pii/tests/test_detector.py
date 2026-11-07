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

    def test_phone_formats(self):
        for text in ('(11) 91234-5678', '+55 11 91234-5678', '11912345678 '):
            expected = 'PHONE<5511912345678>'
            if text.startswith('11912345678'):
                # bare digits without +55 or formatting are not phones
                self.assertNotIn('PHONE', tokenize_text(text, emit))
                self.assertEqual(tokenize_text('+5511912345678', emit), expected)
            else:
                self.assertEqual(tokenize_text(text, emit), expected)

    def test_existing_token_untouched(self):
        self.assertEqual(tokenize_text('CPF#3f1a9c0d22e4', emit), 'CPF#3f1a9c0d22e4')

    def test_protocol_number_not_cpf(self):
        self.assertEqual(tokenize_text('protocolo 20240317551', emit), 'protocolo 20240317551')
