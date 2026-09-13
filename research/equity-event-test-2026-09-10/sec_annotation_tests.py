"""Small offline invariants for source annotations; no providers or outcome data."""
import unittest
from sec_annotate_predecessors import annotate

def event(end,scope='quarter',classification='PRELIMINARY'):
 return {'period_end':end,'classification':classification,'period_evidence':{'period_end':end,'explicit_scopes':[scope]}}
class SourceAnnotationTests(unittest.TestCase):
 def test_other_quarter_does_not_become_known_preliminary(self):
  x=annotate({'current':event('2022-06-30'),'prior_match':{'matched_scope':'quarter'},'information_predecessors':[event('2022-03-31')]})
  self.assertEqual(x['known_preliminary_information'],'UNKNOWN');self.assertEqual(len(x['different_period_disclosures']),1);self.assertEqual(x['information_predecessors'],[])
 def test_unknown_period_remains_unknown_not_absent(self):
  x=annotate({'current':event('2022-06-30'),'information_predecessors':[{'classification':'PRELIMINARY'}]})
  self.assertEqual(x['known_preliminary_information'],'UNKNOWN');self.assertEqual(x['predecessor_coverage']['scope_unresolved_count'],1);self.assertFalse(x['predecessor_coverage']['absence_verified'])
 def test_same_period_scope_retains_known_preliminary(self):
  x=annotate({'current':event('2022-06-30'),'information_predecessors':[event('2022-06-30')]})
  self.assertEqual(x['known_preliminary_information'],'KNOWN_YES');self.assertEqual(len(x['information_predecessors']),1)
 def test_annual_scope_is_not_silently_quarter_scope(self):
  x=annotate({'current':event('2022-12-31'),'prior_match':{'matched_scope':'quarter'},'information_predecessors':[event('2022-12-31','year')]})
  self.assertEqual(x['known_preliminary_information'],'UNKNOWN');self.assertEqual(len(x['different_period_disclosures']),1)
if __name__=='__main__':unittest.main()
