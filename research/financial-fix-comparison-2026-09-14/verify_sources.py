"""Reuse the independent v2 DOM/API numeric auditor on the new payload."""
import importlib.util
from replay import HERE,RAW,V2,intact

spec=importlib.util.spec_from_file_location('independent_v2_source_audit',V2/'audit_provenance.py')
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
original_load=audit.load

def redirected_load(path):
    if path.parent==HERE and path.name in ('filing-plan.json','retrieval-manifest.json'):
        return original_load(V2/path.name)
    return original_load(path)

audit.HERE=HERE
audit.RAW=RAW
audit.load=redirected_load
audit.intact=intact

if __name__=='__main__':audit.main()
