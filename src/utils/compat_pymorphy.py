import importlib
import pkgutil
import sys

import pymorphy3

for m in pkgutil.walk_packages(pymorphy3.__path__, "pymorphy3."):
    try:
        importlib.import_module(m.name)
    except Exception:
        pass

sys.modules.setdefault("pymorphy2", pymorphy3)
for name, mod in list(sys.modules.items()):
    if name.startswith("pymorphy3."):
        sys.modules.setdefault("pymorphy2." + name[len("pymorphy3."):], mod)