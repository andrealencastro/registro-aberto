#!/usr/bin/env python3
"""
Allowlist de campos. Nada fora daqui entra no snapshot publico.

Cada campo declara varios caminhos candidatos porque o schema exato do
endpoint nao foi verificado contra a API real. O primeiro caminho que
existir vence. Se NENHUM existir para um campo REQUIRED, o coletor aborta
em vez de gravar lixo.
"""

# nome_no_snapshot -> caminhos candidatos no payload (dot-notation)
FIELDS: dict[str, list[str]] = {
    "id":                  ["id", "sqCandidato", "sequencialCandidato"],
    "nome_urna":           ["nomeUrna", "nomeCandidato"],
    "numero":              ["numero", "numeroCandidato"],
    "uf":                  ["ufCandidatura", "sgUe", "uf"],
    "cargo_codigo":        ["cargo.codigo", "codigoCargo"],
    "cargo_nome":          ["cargo.nome", "descricaoCargo"],
    "partido_sigla":       ["partido.sigla", "siglaPartido"],
    "partido_numero":      ["partido.numero", "numeroPartido"],
    "situacao_codigo":     ["codigoSituacaoCandidato", "situacao.codigo",
                            "codSituacaoCandidato"],
    "situacao_descricao":  ["descricaoSituacaoCandidato", "situacao.descricao",
                            "nomeSituacaoCandidato", "descSituacaoCandidato"],
    "processo":            ["numeroProcesso", "nrProcesso", "numeroProcessoDrap"],
}

# Sem estes dois o registro nao serve para nada. Ausencia = aborta a coleta.
REQUIRED = ("id", "situacao_descricao")

# Onde procurar a lista de candidaturas dentro do payload.
LIST_KEYS = ("candidatos", "dados", "lista", "items")


def dig(obj, path: str):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def project(record: dict) -> dict:
    """Reduz um candidato aos campos da allowlist."""
    out = {}
    for name, paths in FIELDS.items():
        for p in paths:
            v = dig(record, p)
            if v not in (None, ""):
                out[name] = v
                break
    return out
