"""Use original reference arithmetic; resume already-verified strict artifacts."""
from datetime import datetime,timezone
import json,sys
from prepare import HERE,ROOT,RAW,RECENT,load,sha,write
import worker as w


def main():
    for path,digest in load(HERE/'adapter-freeze.json')['files'].items():assert sha(ROOT/path)==digest,path
    sys.path.insert(0,str(RECENT));import completion as c;import completion_verify as cv
    base_reference=w.reference;base_save=w.save
    def reference(a,u):
        result,paths,check=base_reference(a,u)
        converted='market_sensitive_claim_value' in a['daily'][0]
        original,exact=(c.reference(a,u) if converted else c.original.exposure_reference(a,u))
        assert len(paths)==len(exact)
        max_nav=max_return=0.
        for p,q in zip(paths,exact):
            assert p.keys()==q.keys()
            for field,value in p.items():
                if field=='date':assert value==q[field];continue
                error=abs(value-q[field]);limit=1e-7 if field.endswith('_nav') else 1e-12
                assert error<limit,(field,error)
                if field.endswith('_nav'):max_nav=max(max_nav,error)
                else:max_return=max(max_return,error)
        for field in ('complete','days','first_gap'):assert result[field]==original[field]
        for field in ('ending_nav','selection_difference'):
            if result[field] is None:assert original[field] is None
            else:assert abs(result[field]-original[field])<1e-7
            result[field]=original[field]
        if converted and result['complete']:cv.reference_check(a,exact,u,original)
        check.update(original_reference_paths_used=True,maximum_nav_float_difference=max_nav,maximum_return_or_weight_float_difference=max_return)
        return result,exact,check
    def save(name,obj):
        path=RAW/(name+'.json.gz')
        if path.exists():
            assert load(path)==obj,str(path)
            return dict(file=str(path.relative_to(ROOT)),sha256=sha(path))
        return base_save(name,obj)
    w.reference=reference;w.save=save;sys.argv=[str(HERE/'worker.py'),'recent'];w.main()
    for path,digest in load(HERE/'adapter-freeze.json')['files'].items():assert sha(ROOT/path)==digest,path

if __name__=='__main__':main()
