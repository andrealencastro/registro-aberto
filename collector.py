#!/usr/bin/env python3
"""
Coletor de snapshots das situacoes oficiais de candidatura (DivulgaCandContas/TSE).

Nao interpreta. Nao classifica. Nao cruza bases.
Grava apenas os campos declarados em fields.FIELDS.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

from fields import LIST_KEYS, REQUIRED, project

ROOT = Path(__file__).parent
SNAPSHOTS = ROOT / "snapshots"
METADATA = ROOT / "metadata"
CONFIG = ROOT / "config.json"


class Rejected(Exception):
    """Payload recusado. O snapshot anterior e preservado."""


def find_list(payload: Any) -> list:
    if not isinstance(payload, dict):
        raise Rejected(f"payload nao e objeto ({type(payload).__name__})")
    for k in LIST_KEYS:
        v = payload.get(k)
        if isinstance(v, list):
            return v
    raise Rejected(f"nenhuma chave de lista encontrada em {sorted(payload)[:8]}")


def build_records(payload: Any) -> list[dict]:
    """Valida e projeta. Levanta Rejected em qualquer sinal de resposta ruim."""
    raw = find_list(payload)
    if not all(isinstance(r, dict) for r in raw):
        raise Rejected("lista contem itens que nao sao objetos")

    # Lista vazia com chave reconhecida e resposta LEGITIMA: em julho a
    # maioria dos recortes UF x cargo ainda nao tem candidatura registrada.
    # Recusar isso impede o coletor de comecar. O guarda de encolhimento
    # cuida do caso perigoso (lista cheia que vira vazia).
    if not raw:
        return []

    projected = [project(r) for r in raw]

    # --- auditoria da propria projecao -----------------------------------
    # Uma allowlist contra schema nao verificado pode falhar em silencio e
    # gravar 109 arquivos de registros vazios. Barrar isso e o ponto.
    for key in REQUIRED:
        hit = sum(1 for p in projected if key in p)
        if hit < len(projected) * 0.95:
            sample = sorted(raw[0])[:15]
            raise Rejected(
                f"campo obrigatorio '{key}' resolvido em {hit}/{len(projected)} "
                f"registros — allowlist provavelmente desalinhada do schema. "
                f"Chaves reais do 1o registro: {sample}"
            )

    # 'id' e a chave de todo o resto: analisador, sobreposicao, transicoes.
    # A folga de 5% acima existe so para detectar schema desalinhado com uma
    # mensagem util; um registro sem id e inutilizavel.
    sem_id = [i for i, p_ in enumerate(projected) if "id" not in p_]
    if sem_id:
        raise Rejected(f"{len(sem_id)} registro(s) sem id (indices {sem_id[:5]})")

    ids: list[str] = []
    for i, p_ in enumerate(projected):
        v = p_["id"]
        # bool e int em Python; excluir explicitamente.
        if isinstance(v, bool) or not isinstance(v, (int, str)):
            raise Rejected(f"id nao escalar no registro {i}: {type(v).__name__}")
        ids.append(str(v))

    if len(set(ids)) != len(ids):
        vistos, dup = set(), set()
        for v in ids:
            if v in vistos:
                dup.add(v)
            vistos.add(v)
        raise Rejected("ids duplicados na mesma resposta: "
                       + ", ".join(sorted(dup)[:10]))

    return projected


def ids_of(records: list[dict]) -> set:
    return {r["id"] for r in records if "id" in r}


def check_against_previous(new: list[dict], dest: Path, shrink: float,
                           overlap_min: float) -> None:
    if not dest.exists():
        return
    try:
        old = json.loads(dest.read_text(encoding="utf-8"))["candidaturas"]
    except Exception:  # noqa: BLE001
        return
    if not old:
        return

    if len(new) < len(old) * (1 - shrink):
        raise Rejected(f"coleta encolheu: {len(old)} -> {len(new)} registros")

    old_ids, new_ids = ids_of(old), ids_of(new)
    if old_ids:
        overlap = len(old_ids & new_ids) / len(old_ids)
        if overlap < overlap_min:
            raise Rejected(
                f"sobreposicao de ids caiu para {overlap:.0%} — mesma contagem "
                f"com candidaturas diferentes sugere resposta errada"
            )


def fetch(url: str, timeout: int, tries: int) -> tuple[Any, dict]:
    meta: dict[str, Any] = {"url": url, "attempts": 0}
    headers = {
        "Accept": "application/json",
        "User-Agent": "registro-aberto/0.2 (coletor de dados publicos TSE)",
    }
    for attempt in range(1, tries + 1):
        meta["attempts"] = attempt
        t0 = time.monotonic()
        try:
            r = requests.get(url, timeout=timeout, headers=headers)
            meta["status"] = r.status_code
            meta["elapsed_ms"] = round((time.monotonic() - t0) * 1000)
            meta["bytes"] = len(r.content)
            r.raise_for_status()
            return r.json(), meta
        except Exception as exc:  # noqa: BLE001
            meta["error"] = f"{type(exc).__name__}: {exc}"
            if attempt < tries:
                time.sleep(2 ** attempt)
    return None, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shrink-tolerance", type=float, default=0.30)
    ap.add_argument("--overlap-min", type=float, default=0.80)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not CONFIG.exists():
        print("config.json ausente. Rode discover.py primeiro.", file=sys.stderr)
        return 2

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    targets = cfg["targets"]
    observed = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    run: dict[str, Any] = {
        "observed_at_utc": observed, "targets": len(targets),
        "written": 0, "unchanged": 0, "rejected": 0, "failed": 0,
        "nao_vazios": 0, "results": [],
    }
    SNAPSHOTS.mkdir(exist_ok=True)
    METADATA.mkdir(exist_ok=True)

    for t in targets:
        dest = SNAPSHOTS / t["path"]
        payload, meta = fetch(t["url"], args.timeout, args.tries)
        meta["path"] = t["path"]

        if payload is None:
            run["failed"] += 1
            meta["outcome"] = "failed"
            run["results"].append(meta)
            continue

        try:
            records = build_records(payload)
            check_against_previous(records, dest, args.shrink_tolerance,
                                   args.overlap_min)
        except Rejected as exc:
            run["rejected"] += 1
            meta["outcome"] = "rejected"
            meta["reason"] = str(exc)
            run["results"].append(meta)
            print(f"  RECUSADO {t['path']}: {exc}", file=sys.stderr)
            continue

        records.sort(key=lambda r: str(r.get("id", "")))
        meta["records"] = len(records)
        if records:
            run["nao_vazios"] += 1

        # observado_em fica no snapshot de proposito: e a unica coisa que o
        # arquivo afirma por conta propria, e afirma sobre a observacao,
        # nao sobre quando a decisao ocorreu.
        doc = {
            "fonte": "DivulgaCandContas/TSE",
            "url": t["url"],
            "observado_em_utc": observed,
            "candidaturas": records,
        }
        body = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n"

        # Compara ignorando observado_em_utc, senao todo arquivo muda sempre.
        prev_sig = None
        if dest.exists():
            try:
                prev = json.loads(dest.read_text(encoding="utf-8"))
                prev_sig = json.dumps(prev.get("candidaturas"), sort_keys=True,
                                      ensure_ascii=False)
            except Exception:  # noqa: BLE001
                pass
        cur_sig = json.dumps(records, sort_keys=True, ensure_ascii=False)
        meta["sha256"] = hashlib.sha256(cur_sig.encode()).hexdigest()

        if prev_sig == cur_sig:
            run["unchanged"] += 1
            meta["outcome"] = "unchanged"
        else:
            if not args.dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(body, encoding="utf-8")
            run["written"] += 1
            meta["outcome"] = "written"

        run["results"].append(meta)
        time.sleep(cfg.get("delay_seconds", 1.0))

    if not args.dry_run:
        with (METADATA / "runs.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(run, ensure_ascii=False) + "\n")

    print(f"{observed} | alvos={run['targets']} escritos={run['written']} "
          f"iguais={run['unchanged']} recusados={run['rejected']} "
          f"falhas={run['failed']} nao_vazios={run['nao_vazios']}")

    # Efeito colateral de aceitar lista vazia: a auditoria da allowlist so
    # roda sobre registros reais. Se TUDO veio vazio, a projecao continua
    # sem verificacao — e um schema errado ficaria invisivel ate aparecer
    # a primeira candidatura. Avisar alto.
    if run["nao_vazios"] == 0 and run["failed"] < len(targets):
        print("AVISO: todas as listas vieram vazias. Esperado antes de 15/08, "
              "mas a allowlist de fields.py ainda NAO foi verificada contra "
              "dados reais. Confira a primeira coleta nao vazia.", file=sys.stderr)

    # Recusa generalizada quase sempre significa que o schema mudou.
    if run["rejected"] + run["failed"] > len(targets) * 0.5:
        print("MAIS DE METADE DOS ALVOS RECUSADOS/FALHOS", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
