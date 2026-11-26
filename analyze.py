#!/usr/bin/env python3
"""
Reconstroi transicoes de situacao por candidatura a partir do historico do git.

Isto mede mudanca de candidatura, nao volatilidade de arquivo.
Rode depois de ~2 semanas de coleta.
"""

import collections
import csv
import json
import subprocess
import sys


def sh(*a: str) -> str:
    return subprocess.run(a, capture_output=True, text=True, check=True).stdout


def snapshot_at(commit: str, path: str) -> tuple[str | None, dict]:
    """(observado_em_utc, {id: (situacao, uf, cargo, nome)}) naquele commit."""
    try:
        blob = sh("git", "show", f"{commit}:{path}")
    except subprocess.CalledProcessError:
        return None, {}
    try:
        doc = json.loads(blob)
    except json.JSONDecodeError:
        return None, {}
    out = {}
    for c in doc.get("candidaturas", []):
        if "id" in c:
            out[c["id"]] = (
                c.get("situacao_descricao", "?"),
                c.get("uf", "?"),
                c.get("cargo_nome", "?"),
                c.get("nome_urna", "?"),
            )
    # O horario e o da OBSERVACAO, nao o do commit. O commit pode atrasar
    # com o runner ou o push, e o projeto inteiro se baseia nessa distincao.
    return doc.get("observado_em_utc"), out


def main() -> int:
    commits = sh("git", "log", "--reverse", "--format=%H %cI",
                 "--", "snapshots").splitlines()
    if len(commits) < 2:
        sys.exit("historico insuficiente — deixe o coletor rodar mais tempo")

    paths = sorted(set(sh("git", "ls-files", "snapshots").split()))
    print(f"commits: {len(commits)}   arquivos: {len(paths)}\n")

    transicoes: list[tuple] = []
    entradas = saidas = 0
    ids_vistos: set = set()
    ids_estaveis = collections.Counter()

    for path in paths:
        anterior: dict | None = None   # None = nunca houve snapshot;
                                       # {} = snapshot anterior legitimamente vazio
        for line in commits:
            h, iso = line.split(" ", 1)
            observado, atual = snapshot_at(h, path)
            if observado is None:
                continue
            iso = observado
            if anterior is not None:
                for cid, novo in atual.items():
                    velho = anterior.get(cid)
                    if velho is None:
                        entradas += 1
                    elif velho[0] != novo[0]:
                        transicoes.append((iso, cid, velho[0], novo[0],
                                           novo[1], novo[2], novo[3]))
                saidas += len(set(anterior) - set(atual))
            for cid in atual:
                ids_vistos.add(cid)
                ids_estaveis[cid] += 1
            anterior = atual

    # --- 1. identificadores sao estaveis? --------------------------------
    if ids_estaveis:
        mediana = sorted(ids_estaveis.values())[len(ids_estaveis) // 2]
        efemeros = sum(1 for v in ids_estaveis.values() if v == 1)
        print(f"1. estabilidade de id: {len(ids_vistos)} ids distintos, "
              f"mediana de {mediana} aparicoes, {efemeros} vistos uma vez so")
        if efemeros > len(ids_vistos) * 0.05:
            print("   ATENCAO: muitos ids efemeros — o identificador pode "
                  "nao ser estavel entre coletas")

    # --- 2/3. quantas e quais transicoes ---------------------------------
    print(f"\n2. transicoes de situacao: {len(transicoes)}")
    print(f"   entradas de novas candidaturas: {entradas}")
    print(f"   candidaturas que sumiram da lista: {saidas}")

    pares = collections.Counter((t[2], t[3]) for t in transicoes)
    if pares:
        print("\n3. transicoes mais frequentes:")
        for (de, para), n in pares.most_common(20):
            print(f"   {n:5d}  {de}  ->  {para}")

    # --- 4. ritmo ---------------------------------------------------------
    por_dia = collections.Counter(t[0][:10] for t in transicoes)
    if por_dia:
        print("\n4. transicoes por dia:")
        for d in sorted(por_dia):
            n = por_dia[d]
            print(f"   {d}  {'#' * min(n, 60)} {n}")

    # --- 5. distribuicao --------------------------------------------------
    por_uf = collections.Counter(t[4] for t in transicoes)
    por_cargo = collections.Counter(t[5] for t in transicoes)
    if por_uf:
        print("\n5. por UF:", dict(por_uf.most_common(10)))
        print("   por cargo:", dict(por_cargo.most_common()))

    # --- confiabilidade da fonte -----------------------------------------
    try:
        runs = [json.loads(l) for l in open("metadata/runs.jsonl", encoding="utf-8")]
        alvos = sum(r["targets"] for r in runs)
        f = sum(r["failed"] for r in runs)
        rj = sum(r.get("rejected", 0) for r in runs)
        print(f"\nfonte: {alvos} requisicoes, {f} falhas ({f/max(alvos,1):.1%}), "
              f"{rj} payloads recusados")
    except FileNotFoundError:
        pass

    with open("transicoes.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["observado_em", "id", "de", "para", "uf", "cargo", "nome_urna"])
        w.writerows(transicoes)
    print(f"\ntransicoes.csv gravado ({len(transicoes)} linhas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
