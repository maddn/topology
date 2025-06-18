import os
import importlib

for file in os.listdir(os.path.dirname(__file__)):
    mod_name = file.removesuffix(".py")
    if mod_name in ("__init__", "__pycache__"):
        continue
    importlib.import_module('.' + mod_name, package=__name__)
