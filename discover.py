#!/usr/bin/env python3
"""
Descobre o id da eleicao de 2026 pela propria API e gera config.json.

Uso normal:      python discover.py
Se a API mudar:  python discover.py --eleicao-id <id> --template "<url>"
"""

import argparse
import json
import sys
from pathlib import Path

import requests

BASE = "https://divulgacandcontas.tse.jus.br/divulga/rest/v1"

# Endpoints candidatos para listar eleicoes. O primeiro que responder vence.
ELEICAO_ENDPOINTS = [
    f"{BASE}/eleicao/ordinarias",
    f"{BASE}/eleicao/eleicoes-ordinarias",
    f"{BASE}/eleicao/listar/ordinarias",
]

DEFAULT_TEMPLATE = BASE + "/candidatura/listar/2026/{ue}/{eleicao}/{cargo}/candidatos"

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
       "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
       "SP", "SE", "TO"]

CARGOS = {1: "presidente", 3: "governador", 5: "senador",
          6: "deputado_federal", 7: "deputado_estadual", 8: "deputado_distrital"}


def _achatar(data) -> list[dict]:
    """Aceita lista plana de eleicoes, dict com 'eleicoes', ou lista de dicts
    com 'eleicoes' aninhado. Nenhum de nos verificou qual e o formato real."""
    out: list[dict] = []
    blocos = data if isinstance(data, list) else [data]
    for b in blocos:
        if not isinstance(b, dict):
            continue
        aninhado = b.get("eleicoes")
        if isinstance(aninhado, list):
            out.extend(e for e in aninhado if isinstance(e, dict))
        if "id" in b and ("ano" in b or "nomeEleicao" in b):
            out.append(b)
    return out


def descobrir_eleicao(ano: int) -> int | None:
    for url in ELEICAO_ENDPOINTS:
        try:
            r = requests.get(url, timeout=20,
                             headers={"Accept": "application/json"})
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"  {url} -> {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        eleicoes = [e for e in _achatar(data) if str(e.get("ano")) == str(ano)]
        if not eleicoes:
            print(f"  {url} -> respondeu, mas sem eleicao de {ano}", file=sys.stderr)
            continue

        # Preferencia, nao exigencia: se os codigos nao forem estes, ainda
        # queremos o resultado em vez de falhar.
        federais = [e for e in eleicoes
                    if e.get("tipoEleicao") == "O" and e.get("tipoAbrangencia") == "F"]
        cand = federais or eleicoes

        if len(cand) == 1:
            e = cand[0]
            print(f"  {e.get('nomeEleicao')}  id={e.get('id')}")
            return int(e["id"])

        print(f"  {len(cand)} eleicoes de {ano} encontradas — ambiguo:",
              file=sys.stderr)
        for e in cand:
            print(f"    id={e.get('id')}  {e.get('nomeEleicao')}  "
                  f"tipo={e.get('tipoEleicao')} abrang={e.get('tipoAbrangencia')}",
                  file=sys.stderr)
        print("  escolha com --eleicao-id <id>", file=sys.stderr)
        return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int, default=2026)
    ap.add_argument("--eleicao-id", type=int, default=None,
                    help="pula a descoberta automatica")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE,
                    help="usa {ue}, {eleicao}, {cargo}")
    ap.add_argument("--cargos", default="1,3,5,6,7,8")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    eleicao = args.eleicao_id
    if eleicao is None:
        print("descobrindo id da eleicao...")
        eleicao = descobrir_eleicao(args.ano)
    if eleicao is None:
        print("\nNao foi possivel descobrir o id automaticamente.\n"
              "Abra o DivulgaCandContas com DevTools > Network > XHR, copie a\n"
              "URL de uma listagem e rode:\n"
              "  python discover.py --eleicao-id <id>\n", file=sys.stderr)
        return 2

    cargos = [int(c) for c in args.cargos.split(",")]
    targets = []
    for cargo in cargos:
        if cargo == 1:
            ues = ["BR"]                       # nacional, uma vez so
        elif cargo == 8:
            ues = ["DF"]                       # distrital so no DF
        elif cargo == 7:
            ues = [u for u in UFS if u != "DF"]
        else:
            ues = UFS
        for ue in ues:
            targets.append({
                "ue": ue,
                "cargo": cargo,
                "path": f"{ue}/{cargo}_{CARGOS.get(cargo, cargo)}.json",
                # ue, nao a variavel do laco externo. Este era o bug.
                "url": args.template.format(ue=ue, eleicao=eleicao, cargo=cargo),
            })

    cfg = {"fonte": "DivulgaCandContas/TSE", "ano": args.ano,
           "eleicao_id": eleicao, "delay_seconds": args.delay,
           "targets": targets}
    Path("config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    por_cargo = {}
    for t in targets:
        por_cargo[CARGOS.get(t["cargo"], t["cargo"])] = \
            por_cargo.get(CARGOS.get(t["cargo"], t["cargo"]), 0) + 1
    print(f"\nconfig.json: {len(targets)} alvos  {por_cargo}")
    print("Confira uma URL a olho nu antes de agendar:")
    print(" ", targets[0]["url"])
    print("Depois:  python collector.py --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
