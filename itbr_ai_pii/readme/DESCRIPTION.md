Neutral core that keeps clients' personal data out of an AI provider, as LGPD
asks. It detects CPF and CNPJ (valid check digits), e-mail and Brazilian phone
numbers in text and swaps each value for a stable token such as `CPF#1a2b3c4d5e6f`.

A token is `KIND#` plus 12 hex digits of an HMAC-SHA256 of the normalized value,
so the same value always gives the same token and the real value cannot be
recovered from it. Kinds are `CPF`, `CNPJ`, `EMAIL`, `PHONE`, `NAME`, `ADDR`,
`DATE` and `DOC`.

This module depends only on `base`. It ships the detector and the key handling;
other modules plug it into their AI integrations.
