"""Fork HOM step modules to the MHM step package."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "main_access",
    "login_move",
    "phone_login",
    "kakao_login",
    "contract_list",
    "contract_detail",
    "compensation_charge",
    "compensation_result",
    "compensation_cancel",
    "compensation_result_common",
    "long_term_policy_certificate",
]

HOM_STEPS = ROOT / "app" / "systems" / "hom" / "steps"
MHM_STEPS = ROOT / "app" / "systems" / "mhm" / "steps"

for name in FILES:
    src = HOM_STEPS / f"{name}.py"
    dst = MHM_STEPS / f"{name}.py"
    text = src.read_text(encoding="utf-8")
    text = text.replace("from . import login_common as common", "from . import login_common as common")
    dst.write_text(text, encoding="utf-8")
    print("wrote", dst.name)
