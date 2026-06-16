import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"


def normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_requirements(path: Path) -> set[str]:
    required: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pkg = re.split(r"[<>=!~ ]", line, maxsplit=1)[0].strip()
        if pkg:
            required.add(normalize_package_name(pkg))
    return required


def installed_packages() -> set[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    packages = json.loads(result.stdout)
    return {normalize_package_name(item["name"]) for item in packages}


def main() -> int:
    if not REQUIREMENTS_FILE.exists():
        print(f"Missing requirements file: {REQUIREMENTS_FILE}")
        return 2

    required = read_requirements(REQUIREMENTS_FILE)
    installed = installed_packages()
    missing = sorted(required - installed)

    print(f"Required packages: {len(required)}")
    print(f"Installed packages: {len(installed)}")
    if missing:
        print("Missing packages:")
        for pkg in missing:
            print(f"- {pkg}")
        return 1

    print("All required packages are installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
