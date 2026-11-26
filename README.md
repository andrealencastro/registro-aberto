# registro-aberto — coletor

Série temporal das situações oficiais de registro de candidatura,
Eleições Gerais 2026, a partir do DivulgaCandContas/TSE.

**O que é:** snapshots datados de um punhado de campos públicos, versionados no git.

**O que não é:** não interpreta decisões, não classifica elegibilidade, não cruza
com bases de condenações, não afirma nada sobre pessoa alguma. A denominação da
situação é reproduzida literalmente como publicada pelo TSE.

## Estado (novembro de 2026)

- O schema da listagem de candidaturas **não foi verificado contra a API
  real**, e este repositório ainda não contém nenhuma coleta. O primeiro passo
  é `python collector.py --dry-run`: se a allowlist estiver desalinhada, o
  coletor recusa a resposta e imprime as chaves reais do payload.
- O período de registro de candidaturas de 2026 já passou. As referências de
  calendário mais abaixo ("antes de 15/08") descrevem o ciclo para o qual o
  coletor foi escrito.
- O agendamento do workflow vem **desligado** (ver *Uso*).

## Estrutura

    collector.py                    coleta e grava snapshots/ e metadata/
    fields.py                       allowlist de campos e projeção
    discover.py                     descobre o id da eleição e gera config.json
    analyze.py                      transições por candidatura, pelo histórico do git
    test_collector.py               testes das defesas com payloads sintéticos
    config.json                     eleição 20322002026 e os 109 alvos UF×cargo
    .github/workflows/capture.yml   coleta pelo GitHub Actions

## Uso

    pip install -r requirements.txt

    # config.json já vem versionado. Só rode discover.py se precisar refazê-lo:
    python discover.py                # descobre o id da eleição pela API
                                      # (ou: --eleicao-id <id>)
    python collector.py --dry-run     # confira antes de agendar
    python collector.py
    python test_collector.py          # 23 asserções, sem rede

Depois de ~2 semanas: `python analyze.py` → transições por candidatura + `transicoes.csv`

O workflow `capture` roda sob demanda (Actions → capture → Run workflow). O
agendamento, nos minutos 17 e 47 de cada hora, vem comentado em
`.github/workflows/capture.yml`: descomente o bloco `schedule` depois de
conferir o `--dry-run`.

## Allowlist

Só entram no snapshot os campos declarados em `fields.py`: id, nome de urna,
número, UF, cargo, partido, situação e número do processo. CPF, data de
nascimento, raça/cor, bens, e-mails e fotos são descartados na projeção — não
são necessários para a finalidade e não devem ser republicados.

`fields.py` declara vários caminhos candidatos por campo porque o schema real
não foi verificado. Se a projeção resolver menos de 95% dos registros para `id`
ou `situacao_descricao`, o coletor **recusa** a resposta e imprime as chaves
reais do payload — em vez de gravar 109 arquivos vazios em silêncio.

## Guardas antes de sobrescrever

| Condição | Ação |
|---|---|
| payload não é objeto / sem chave de lista | recusa |
| lista vazia **com** chave reconhecida | aceita (baseline) |
| registro sem `id`, `id` não escalar, `id` duplicado | recusa |
| itens não são objetos | recusa |
| allowlist resolve < 95% dos required | recusa |
| coleta encolheu > 30% | recusa |
| sobreposição de ids < 80% | recusa |
| > 50% dos alvos recusados/falhos | exit 1 |

Recusa preserva o snapshot anterior. Uma resposta 200 truncada é pior que um
erro: contamina a série em silêncio.

Lista vazia é **aceita**: antes de 15/08 a maioria dos 109 recortes UF×cargo
está legitimamente sem candidatura, e recusá-las impediria a série de começar.
O guarda de encolhimento cobre o caso perigoso (lista cheia que vira vazia).
Efeito colateral: enquanto tudo vier vazio, a allowlist não é exercitada — o
coletor avisa em `stderr` que a projeção segue não verificada.

## Limites

- O snapshot registra **quando foi observado**, não quando a decisão ocorreu.
- O git **não é imutável**. Se auditabilidade importar: proteger a branch,
  bloquear force push, assinar commits, espelhar em outro host, publicar o
  hash do HEAD em local independente.
- O workflow faz `git add` **antes** do teste de mudança: `git diff` não
  enxerga arquivo não rastreado, e na primeira execução todos são novos.
- `config.json` **está versionado neste repositório** (eleição 20322002026, 109
  alvos). O workflow só chama `discover.py` se o arquivo sumir, para que uma
  queda daquele endpoint não derrube a coleta de candidaturas.
- `id` duplicado recusa o recorte UF×cargo inteiro. É deliberado — sobrescrita
  silenciosa no analisador é pior que uma lacuna visível —, mas se acontecer com
  frequência na coleta real, é a primeira regra a reavaliar.
- O workflow só commita quando `snapshots/` muda. Métricas de execuções sem
  mudança vão para artefatos do Actions, não para o histórico.
- A fonte oficial e atual é sempre o DivulgaCandContas.

## Licença

Dados: públicos, do TSE. Código: MIT (ver `LICENSE`).
