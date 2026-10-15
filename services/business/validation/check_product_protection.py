"""Check this SDD's product source boundary against its approved Git baseline."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = 'ca25864361d7b3177efe8bacc6412c105f52031d'
PATHS = ['services/business/backend/portal/product_*.py',
         'services/business/backend/portal/product_assets', 'frontend/src/business/product']

if __name__ == '__main__':
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--', *PATHS], cwd=ROOT, text=True)
    added = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--', *PATHS], cwd=ROOT, text=True)
    if changed or added:
        print('Product protection failed:\n' + changed + added)
        sys.exit(1)
    print('PASS: protected product backend, assets and frontend match ' + BASE)
