"""Fork hom_*.py step modules to mhm_*.py"""
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

for name in FILES:
    src = ROOT / f"hom_{name}.py"
    dst = ROOT / f"mhm_{name}.py"
    text = src.read_text(encoding="utf-8")
    text = text.replace("hom_login_common", "mhm_login_common")
    text = text.replace("hom_compensation_result_common", "mhm_compensation_result_common")
    text = text.replace("import hom_", "import mhm_")
    dst.write_text(text, encoding="utf-8")
    print("wrote", dst.name)
