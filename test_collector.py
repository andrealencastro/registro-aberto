"""Testa as defesas com payloads sinteticos. Nao toca a rede."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from collector import build_records, check_against_previous, Rejected

def cand(i, sit="AGUARDANDO JULGAMENTO"):
    return {"id": i, "nomeUrna": f"FULANO {i}", "numero": 10000+i,
            "ufCandidatura": "SP", "cargo": {"codigo": 6, "nome": "Deputado Federal"},
            "partido": {"sigla": "XXX", "numero": 99},
            "codigoSituacaoCandidato": 2, "descricaoSituacaoCandidato": sit,
            "numeroProcesso": f"0600{i}",
            # ruido que a allowlist tem de descartar:
            "cpf": "12345678900", "dataNascimento": "1980-01-01",
            "corRaca": "PARDA", "bens": [{"valor": 1000000}],
            "emails": ["x@y.com"], "fotoUrl": "http://.../a.jpg"}

ok = fail = 0

def _rejeita(payload):
    try:
        build_records(payload); return False
    except Rejected:
        return True
def check(nome, cond):
    global ok, fail
    if cond: ok += 1; print(f"  PASS {nome}")
    else:    fail += 1; print(f"  FAIL {nome}")

print("allowlist:")
r = build_records({"candidatos": [cand(1), cand(2)]})
check("projeta os campos declarados", r[0]["situacao_descricao"] == "AGUARDANDO JULGAMENTO")
check("descarta cpf",        "cpf" not in r[0])
check("descarta nascimento", "dataNascimento" not in r[0])
check("descarta raca",       "corRaca" not in r[0])
check("descarta bens",       "bens" not in r[0])
check("descarta email",      "emails" not in r[0])
check("so campos da allowlist", set(r[0]) <= {
    "id","nome_urna","numero","uf","cargo_codigo","cargo_nome",
    "partido_sigla","partido_numero","situacao_codigo","situacao_descricao","processo"})

print("\nvalidacao de payload:")
for nome, p in [("objeto vazio", {}),
                ("erro com 200", {"erro": "indisponivel"}),
                ("lista de strings", {"candidatos": ["a","b"]}),
                ("payload nao-objeto", ["a"])]:
    try:
        build_records(p); check(nome, False)
    except Rejected: check(nome, True)

print("\nauditoria da projecao (schema desalinhado):")
try:
    build_records({"candidatos": [{"nomeDoCandidato":"X","statusRegistro":"OK"}]*10})
    check("schema desconhecido e recusado", False)
except Rejected as e:
    check("schema desconhecido e recusado", "allowlist" in str(e))
    print(f"       -> {str(e)[:95]}...")

print("\nlista vazia legitima (fase pre-registro):")
check("lista vazia inicial e aceita", build_records({"candidatos": []}) == [])
check("payload sem chave de lista ainda recusa", _rejeita({"x": 1}))

print("\nguardas contra snapshot anterior:")
tmp = Path(tempfile.gettempdir()) / "registro_aberto_snap.json"
base = [dict(r, id=i) for i, r in enumerate([build_records({"candidatos":[cand(i)]})[0] for i in range(100)])]
tmp.write_text(json.dumps({"candidaturas": base}), encoding="utf-8")

try:
    check_against_previous(base[:50], tmp, 0.30, 0.80); check("encolhimento 50% barrado", False)
except Rejected: check("encolhimento 50% barrado", True)
try:
    check_against_previous(base[:90], tmp, 0.30, 0.80); check("encolhimento 10% passa", True)
except Rejected: check("encolhimento 10% passa", False)
try:
    check_against_previous([], tmp, 0.30, 0.80)
    check("lista cheia que vira vazia e barrada", False)
except Rejected: check("lista cheia que vira vazia e barrada", True)
outros = [dict(c, id=c["id"]+9000) for c in base]
try:
    check_against_previous(outros, tmp, 0.30, 0.80); check("ids trocados barrado", False)
except Rejected as e: check("ids trocados barrado", "sobreposicao" in str(e))
tmp.unlink(missing_ok=True)

print("\nids problematicos:")
check("ids duplicados sao recusados",
      _rejeita({"candidatos": [cand(1), cand(1), cand(2)]}))
check("id nao escalar e recusado",
      _rejeita({"candidatos": [dict(cand(i), id={"n": i}) for i in range(10)]}))
check("id booleano e recusado",
      _rejeita({"candidatos": [dict(cand(i), id=True) for i in range(10)]}))
sem = [cand(i) for i in range(20)]
for r in sem[:1]:
    del r["id"]
check("registro sem id e recusado", _rejeita({"candidatos": sem}))
check("id string e aceito",
      len(build_records({"candidatos": [dict(cand(i), id=f"C{i}") for i in range(5)]})) == 5)

print(f"\n{ok} passaram, {fail} falharam")
sys.exit(1 if fail else 0)
