"""
Initialise le registre Bidoo depuis un fichier JSON externe.
Usage sur le serveur :
  python /opt/almanak/current/infrastructure/scripts/init_bidoo_pionniers.py /opt/almanak/data/pionniers_import.json

Le fichier JSON doit contenir : {"emis": [{virga, prenom, temp_pass, utilise}, ...]}
Les entrées déjà présentes (même virga) sont ignorées.
"""
import json, sys
from pathlib import Path

REGISTRE = Path("/opt/almanak/data/registre_bidoo.json")
GLYPHES = ['∅', '|', '∧', '✕', '⊏', '⋈']

def virga_code(num):
    n = num - 1
    return ' '.join(GLYPHES[x] for x in [n//216, (n%216)//36, (n%36)//6, n%6])

source = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if not source or not source.exists():
    print("Usage : python init_bidoo_pionniers.py <fichier.json>")
    sys.exit(1)

import_data = json.loads(source.read_text(encoding="utf-8"))
registre = json.loads(REGISTRE.read_text(encoding="utf-8")) if REGISTRE.exists() else {"emis": []}
existants = {int(b["virga"]) for b in registre["emis"]}
ajoutes = 0

for p in import_data.get("emis", []):
    if int(p["virga"]) not in existants:
        registre["emis"].append(p)
        ajoutes += 1
        print(f"  + Bidoo #{p['virga']} ({virga_code(p['virga'])}) — {p['prenom']}")
    else:
        print(f"  ~ Bidoo #{p['virga']} déjà présent, ignoré")

REGISTRE.write_text(json.dumps(registre, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n{ajoutes} Bidoo(s) ajouté(s). Registre : {len(registre['emis'])} entrée(s).")
