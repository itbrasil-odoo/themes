# ServIAm: dados pessoais fora do provedor de IA (`itbr_muk_ai_pii`)

Data: 2026-11-07. Odoo 19.0. Repositório: `itbrasil-odoo/themes` (fork do MuK).

## Intenção e porquê

O time do Grupo Dedicata e de clientes (Jotareis e outros, com e sem Enterprise) vai conversar com o
assistente de IA do Odoo (MuK AI, chamado ServIAm em pt_BR) para tirar relatórios, abrir telas e tirar
dúvidas. São pessoas que não conhecem o sistema e conversam em linguagem natural. O que o assistente lê do
Odoo vai para a Anthropic. Pela LGPD, dado pessoal deve sair do Odoo só no mínimo necessário.

A ideia vem do plugin [pii-tokens](https://github.com/oLucasAguilar/pii-tokens) (MIT), que o time de
desenvolvimento também vai usar: trocar o dado pessoal por um token antes de o modelo ler, mantendo o
mesmo token para o mesmo valor (o modelo ainda conta, agrupa e compara), e trocar de volta para quem está
conversando.

**Decisões do Renan (2026-11-06/07):**
- O usuário vê os valores **reais** na tela; o Claude só vê tokens.
- Vira token: dado de **pessoa física** (nome de contato pessoa física, CPF, e-mail, telefone, endereço,
  data de nascimento) e **todo CNPJ** (CNPJ de MEI e de empresário individual identifica uma pessoa).
  Razão social de empresa fica legível.
- Não é uma lista manual de campos: o controle é por regras automáticas que sobrevivem às atualizações dos
  apps, com o admin registrando só exceções.
- Áreas bloqueadas por padrão (o Claude nem sabe que existem): **RH e folha** e **dados bancários**.
- Nomes do **próprio time** (usuários e funcionários: vendedor, responsável, quem aprovou) ficam
  **legíveis**. Só clientes e contatos pessoa física viram `NAME#`.
- Documentos (PDF, relatório impresso, anexo) **não são bloqueados**: o usuário é avisado do risco e
  confirma antes de o conteúdo ir ao provedor.
- Formato do token igual ao do pii-tokens e ao que a sessão da v20 (`ai_enterprise`) vai usar: `TIPO#12hex`.

## Objetivos

1. Nenhum CPF, CNPJ, e-mail, telefone, endereço ou data de nascimento, e nenhum nome de cliente ou contato
   pessoa física, lido do Odoo chega ao provedor em claro, em nenhum caminho que use `muk_ai.session`
   (chat, subagentes, compactação, chatter, automação, decisão). Exceções: nomes do próprio time, e
   documentos que o usuário confirmou ou anexou (seção 5).
2. Respostas e ações continuam funcionando: "faturamento por cliente", "abra o contato do CPF X", criar ou
   editar registros usando dados que o modelo só conhece por token.
3. Campo novo, de app novo ou atualizado, é classificado sozinho.
4. Uma área bloqueada (RH/folha, bancos) não é lida pela IA, nem para quem a vê na tela.

## Fora do escopo (não-objetivos)

- Clientes MCP externos (Claude Desktop/Code pelo `/mcp` do `muk_mcp`): lá não há como destokenizar a
  resposta. Os **bloqueios** de área e de campo valem também para eles; os **tokens**, não.
- Conteúdo binário: imagens, PDFs e anexos (inclusive os que o usuário anexa à conversa) não passam por
  OCR. Ver "Documentos e relatórios".
- Anonimização: o token é pseudônimo. O mapa token → valor existe no servidor.
- Segredos (chaves de API, senhas): já tratados pelo `itbr_muk_ai_guard`.
- Trava de região (`inference_geo`) e de modelos com retenção de 30 dias: rodada seguinte.

## Anti-objetivos (falha mesmo se "funcionar")

- O usuário passar a ver `CPF#...` na resposta ou nos cartões de ferramenta.
- O assistente ficar inútil para relatório por cliente pessoa física (o token tem de agrupar).
- Uma atualização de app expor um campo novo de dado pessoal sem ninguém perceber.
- O token ser revertido sem o servidor (hash simples de CPF se reverte por dicionário).
- Cobrar uma rodada do provedor duas vezes por causa do mascaramento.

## Restrições

- Fork do MuK sincronizado com o upstream com frequência: o código fica num módulo próprio
  (`itbr_muk_ai_pii`, depende de `muk_ai` e `muk_mcp`), com ganchos mínimos no fork só onde não houver
  ponto de extensão, cada um em commit próprio e reaplicável.
- Odoo 19, Community e Enterprise.
- Chave de HMAC fora do banco, pela convenção já usada para chaves de IA: env `ODOO_AI_PII_KEY`, depois
  `ai_pii_key` no `odoo.conf`. Sem chave, o módulo **não liga** os tokens e avisa nas configurações
  (nunca usa uma chave guardada no banco).
- Testes sem rede, no padrão do `muk_ai` (`AITestCommon`).

## Como funciona

### 1. Três camadas de decisão

**a) Áreas bloqueadas (modelo).** Lista de modelos inteiros que a IA não lê (sem filtro por registro).
Padrão, para os que existirem na base: RH/folha (`hr.contract`, `hr.version`, `hr.payslip`,
`hr.payslip.line`, `hr.payslip.run`, `hr.salary.attachment`) e dados bancários (`res.partner.bank`,
`payment.token`). Campos privados de `hr.employee` saem pela camada b. O admin pode acrescentar ou retirar
modelos. Uma chamada de ferramenta a um modelo bloqueado recebe o mesmo erro de
"modelo não permitido" do `muk_mcp_access`, sem revelar o motivo.

**b) Classificação dos campos.** Cada campo (`ir.model.fields`) tem uma exposição para a IA:
`liberado`, `tokenizado` ou `bloqueado`. O valor vem de regras pelo nome e tipo do campo, e o admin só
sobrescreve as exceções (campo `ai_exposure_override`, que sobrevive às atualizações):
- bloqueado: `password`, `*_token`, `acc_number`, `iban`, `bank_*`, `wage`, `salary`, `private_*`,
  `ssnid`, `passport_id`, `identification_id`, campos binários de documentos de RH;
- tokenizado: `vat`, `cnpj_cpf`, `cpf*`, `cnpj*`, `email*`, `phone`, `mobile`, `street*`, `zip`,
  `birthday`, `birth*`, e campos de texto que copiam nome de cliente (`contact_name`, `partner_name`,
  `invoice_partner_display_name`, `*_partner_name`). Vale para pessoa física **e** empresa: o detector da
  camada c tokeniza qualquer e-mail ou telefone sem saber de quem é, e a regra uniforme é a coerente
  *(escolha do desenho)*. `city`, `state_id` e `country_id` ficam legíveis (relatório por região);
- liberado: o resto.
A classificação é recalculada quando um módulo é instalado ou atualizado, e é visível numa lista
"Exposição dos campos à IA" (filtrável) para auditoria.

**c) Detector no valor.** Todo texto que vai ao provedor passa por um detector, independente do campo:
CPF e CNPJ com dígito verificador válido, e-mail, telefone brasileiro. Pega dado pessoal em texto livre
(notas, chatter, descrição) e em campo que a camada b classificou mal. Porte das regras do
`plugin/scripts/pii.py` do pii-tokens (MIT, com crédito).

**Nome de pessoa física.** Não dá para decidir pelo campo: `res.partner.name` é razão social numa empresa e
nome de gente num contato. Regra: o nome (e o `display_name`, inclusive em Many2one e no bloco de contexto
do registro aberto na tela) de um `res.partner` com `is_company = False` vira `NAME#`; com
`is_company = True`, fica legível. **Exceção:** parceiro ligado a um usuário interno (`user_ids` com
`share = False`) ou a um funcionário fica legível — nome do próprio time (decisão do Renan). Many2one para
`res.users` e `hr.employee`, o autor de mensagens internas e o nome do usuário no prompt de sistema também
ficam legíveis; o `login` de usuário é tratado como e-mail. O texto livre fica a cargo do detector, que
não pega nomes (limitação aceita, como no pii-tokens).

### 2. Onde cada camada atua

- **Leitura de registros** (`muk_mcp` `_mcp_read`, usado por `search_read` e `read_records`; e
  `read_group`, `export_records`): campos bloqueados saem do resultado e do `fields_get`/`describe_model`;
  campos tokenizados saem como token; Many2one para `res.partner` pessoa física sai com `NAME#`.
  Isso vale para o chat e para clientes MCP externos (sem tokens no externo: lá o campo tokenizado sai
  **bloqueado**).
- **Fronteira com o provedor** (`muk_ai.session._build_request_inputs`/`_materialize_round_inputs`, e
  toda outra chamada ao provedor feita por uma sessão, como a compactação): o detector roda em todo texto
  que sai — resultado de ferramenta, mensagem do usuário, bloco de contexto de tela/registro, sugestões,
  resumo da compactação. Vale para todo caminho que roda sobre `muk_ai.session` (chat, subagentes,
  chatter, automação, decisão) *(escolha do desenho)*.
- **Volta do provedor:**
  - texto em streaming (`_on_stream_delta`): os tokens são trocados pelos valores reais antes de publicar
    ao navegador. Um token pode chegar partido entre dois deltas: segura a cauda que pareça início de
    token até completar ou ficar claro que não é token;
  - argumentos de ferramenta: destokenizados antes de executar (`_dispatch_tool_call`), para que busca por
    CPF, criação de registro e `message_post` usem o valor real; e antes de mostrar a prévia de aprovação;
  - conversa persistida: guarda o que o provedor viu (com tokens), para a reprodução das rodadas e o cache
    de prompt continuarem iguais. A tela renderiza destokenizado (`get_snapshot`, eventos, histórico).
  - tudo que a IA grava no Odoo sai destokenizado: argumentos de ferramenta, texto inserido no editor ou
    postado no chatter/Discuss (`muk_ai_chatter`), saída de automação e de decisão. Nenhum `NAME#`/`CPF#`
    pode acabar gravado em dado de negócio.

### 3. Tokens e mapa

- Token: `TIPO#` + 12 hex de `HMAC-SHA256(chave, tipo + ":" + valor normalizado)`. Tipos: `CPF`,
  `CNPJ`, `EMAIL`, `PHONE`, `NAME`, `ADDR`, `DATE`, `DOC` (outros campos tokenizados).
- Normalização antes do HMAC: CPF/CNPJ só dígitos, e-mail minúsculo, telefone E.164, nome com espaços
  colapsados. Assim "123.456.789-09" e "12345678909" viram o mesmo token.
- Determinístico **por base** (mesma chave): o mesmo cliente tem o mesmo token em todas as conversas
  *(escolha do desenho)*.
- Mapa token → valor: tabela `itbr.muk_ai.pii.token` (token, tipo, valor) e a relação de quais sessões
  emitiram cada token. Uma entrada some quando nenhuma sessão que a emitiu existe mais (retenção do
  `muk_ai`).
- Destokenizar para uma sessão usa um token que tenha sido emitido para uma sessão **do mesmo usuário** ou
  da **mesma árvore de subagentes** (mãe e filhas) *(escolha do desenho)*. Token inventado ou emitido só
  para outro usuário não é revelado: aparece como está.
- Acesso: a tabela é só do sistema (sudo interno); nenhum usuário lê pela interface ou RPC.

### 4. Configuração (Configurações > ServIAm > Dados pessoais)

- Ligar/desligar tokens (desligado sem chave de HMAC no servidor, com aviso).
- Lista de modelos bloqueados (já preenchida com RH/folha e bancos).
- Botão para a lista "Exposição dos campos à IA", com as exceções do admin.
- Domínios de e-mail liberados (ex.: o domínio da própria empresa), como no pii-tokens.

### 5. Documentos e relatórios

Conteúdo binário (PDF, imagem, relatório impresso, anexo) não passa pelo mascaramento: não há OCR. Decisão
do Renan: não bloquear, mas avisar e pedir confirmação.

- **Documento que a IA busca** (`print_report`, `read_resource`/leitura de anexo de registro, imagem de
  registro): com os tokens ligados, a chamada passa pelo mesmo cartão de aprovação das gravações (risco
  novo no `muk_ai.approval._assess_risk`), com o motivo: "Este documento pode conter dados pessoais (CPF,
  endereço, nome) que vão ao provedor de IA sem mascaramento." Aprovar uma vez, aprovar para a sessão
  (mesma assinatura ferramenta + modelo) ou recusar. A pausa vale mesmo que o "Aprovar toda gravação" do
  guard esteja desligado; só o modo de aprovação `off` de um admin a dispensa.
- **Anexo que o usuário coloca na conversa:** vai como está, sem confirmação, porque o usuário já escolheu
  enviar; o chip do anexo mostra um aviso curto do mesmo risco *(escolha do desenho)*.
- Bloqueio de área (camada a) continua valendo: documento de modelo bloqueado não é lido nem com aprovação.

## Testes de aceite

1. `search_read` de `res.partner` pessoa física: o provedor recebe `NAME#`, `CPF#`, `EMAIL#`, `PHONE#`;
   empresa: razão social legível, `CNPJ#`.
2. O mesmo CPF formatado de dois jeitos gera o mesmo token.
3. O modelo pede `search_read` com domínio `[('vat', '=', 'CPF#...')]`: a ferramenta recebe o CPF real e
   acha o registro.
4. Streaming: um token partido em dois deltas aparece real na tela, inteiro.
5. Resposta final e histórico mostram valores reais; a conversa guardada tem tokens.
6. `hr.payslip`/`res.partner.bank` não aparecem para a IA (nem no `describe_model`) para um admin.
6b. Nome de vendedor (usuário interno) e de contato ligado a funcionário saem legíveis; contato pessoa
    física de cliente sai `NAME#`.
6c. `print_report` de uma fatura pausa com o aviso de dados pessoais; aprovado para a sessão, a segunda
    fatura passa direto; recusado, o modelo recebe a recusa e nada sai.
6d. Mensagem postada no chatter pela IA e saída de automação não contêm `NAME#`/`CPF#`.
6e. Subagente: token emitido na filha é destokenizado na mãe; token de sessão de outro usuário não é.
7. Campo `x_cpf_responsavel` criado depois da instalação nasce `tokenizado`; exceção do admin sobrevive a
   `-u`.
8. CPF numa nota de chatter lida pelo modelo vira token.
9. Token de outra sessão não é destokenizado.
10. Sem chave de HMAC: tokens desligados, aviso nas configurações, bloqueios continuam valendo.
11. Cliente MCP externo: campo tokenizado sai bloqueado.
12. Nenhuma chamada extra ao provedor por causa do mascaramento (conta de rodadas igual com e sem o módulo).

## Fica a critério de quem construir

Nomes internos, estrutura de arquivos, a forma de ganchar `_mcp_read` e os pontos de streaming (preferir
herança; gancho no fork só se não houver ponto de extensão, em commit próprio), o porte exato das regexes do
pii-tokens, desempenho do detector em resultados grandes.

## Decisões tomadas na revisão do desenho (2026-11-07)

Do Renan: nomes do próprio time legíveis; documentos com aviso e confirmação em vez de bloqueio.

Escolhas do desenho (conferir): mascaramento em todo caminho sobre `muk_ai.session`, inclusive compactação,
com destokenização de tudo que a IA grava no Odoo; token determinístico por base e destokenização limitada
ao mesmo usuário ou à árvore de subagentes; bloqueio de área só por modelo inteiro (sem `hr.leave`);
e-mail, telefone e endereço tokenizados também para empresas, cidade legível; campos que copiam nome de
cliente tokenizados sempre; anexo do usuário sem confirmação, só com aviso.
