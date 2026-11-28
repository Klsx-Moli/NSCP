"""Create the hard/no-lexical-overlap variant of the differential harness."""
import pathlib

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
src = (E / "multiengine_differential.py").read_text(encoding="utf-8")
old = '''QUERIES = [
    ("q1", "quien revoco el permiso de push a las 10:00", "d00"),
    ("q2", "error file or directory not found en el test", "d05"),
    ("q3", "vector de 1024 dimensiones del embedding", "d02"),
]'''
new = '''QUERIES = [
    ("h1", "quien anulo la autorizacion para enviar cambios", "d00"),
    ("h2", "no se encontro el modulo del agente", "d05"),
    ("h3", "tamaño del vector de similitud", "d02"),
    ("h4", "who revoked the push authorization at ten", "d00"),
]'''
assert old in src
src = src.replace(old, new)
src = src.replace("MULTIENGINE_DIFFERENTIAL.json", "MULTIENGINE_DIFFERENTIAL_HARD.json")
src = src.replace('"diff-', '"hard-')
src = src.replace('"sha": "97ea9e9"', '"sha": "97ea9e9", "variant": "hard_no_lexical_overlap"')
(E / "multiengine_differential_hard.py").write_text(src, encoding="utf-8")
print("hard variant written")
