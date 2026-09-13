"""Regression for registered source-missing slots; synthetic data only."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

PATH=Path(__file__).resolve().parents[1]/'research/equity-event-expansion-2026-09-13/model.py'
spec=importlib.util.spec_from_file_location('equity_event_expansion_model_audit',PATH)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


def development():
    return [{'event_id':f'{year}:{i}','cik':str(i),'status':'READY',
        'entry_date':f'{year}-06-01','exit_date':f'{year}-06-29',
        'features':{'value':float(i%9),'scope':'quarter'},
        'current_text':'growth margin outlook' if i%2 else 'caution debt outlook',
        'prior_text':'legacy operations business','target_pp':float(i%9)/5}
        for year,n in [(2020,200),(2021,100)] for i in range(n)]


def missing_slot():
    return {'event_id':'registered:missing','cik':'999','status':'UNRESOLVED',
            'entry_date':None,'exit_date':None,'target_pp':None,
            'features':{},'current_text':'','prior_text':''}


def test_missing_source_slot_survives_without_changing_any_fitted_model():
    source=development()
    clean,clean_report=m.select_and_refit(source)
    full=source+[missing_slot()];before=deepcopy(full)
    actual,report=m.select_and_refit(full)
    assert full==before
    assert report==clean_report
    for key in clean:
        assert actual[key].training_event_ids==clean[key].training_event_ids
        np.testing.assert_array_equal(actual[key].estimator.coef_,clean[key].estimator.coef_)


def test_missing_slot_does_not_hide_an_unmasked_evaluation_target():
    future=deepcopy(development()[0])
    future.update(event_id='future',entry_date='2022-06-01',exit_date='2022-06-29')
    with pytest.raises(ValueError,match='Evaluation targets must remain masked'):
        m.select_and_refit([missing_slot()]+development()+[future])
