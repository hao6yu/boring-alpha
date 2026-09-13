"""Chronology and preprocessing checks using invented rows, never price labels."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest


PATH = Path(__file__).resolve().parents[1]/'research/equity-event-test-2026-09-10/model.py'
spec = importlib.util.spec_from_file_location('equity_event_model_audit', PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def rows(year=2020, n=30):
    return [{'event_id': f'{year}:{i}', 'cik': str(i),
             'entry_date': f'{year}-06-01', 'exit_date': f'{year}-06-29',
             'status': 'READY',
             'features': {'metric': None if i % 4 == 0 else float(i % 11),
                          'second': float(i % 7), 'scope': 'quarter' if i % 2 else 'annual'},
             'current_text': 'growth margin outlook' if i % 2 else 'caution debt outlook',
             'prior_text': 'legacy operations business',
             'target_pp': float((i % 11)*.2 + (i % 2)*.3)} for i in range(n)]


def test_maturity_and_prediction_dates_block_crossing_the_fit_cutoff():
    sample = rows()
    boundary = deepcopy(sample[0]); boundary.update(event_id='late2020', entry_date='2020-12-21', exit_date='2021-01-20')
    assert boundary not in m.matured(sample+[boundary], 2020, '2020-12-31')
    assert boundary in m.matured(sample+[boundary], 2020, '2021-12-31')
    with pytest.raises(ValueError, match='Unmatured'):
        m.Regressor(False, .1).fit(sample+[boundary], '2020-12-31')
    fitted = m.Regressor(False, .1).fit(sample, '2020-12-31')
    with pytest.raises(ValueError, match='Prediction date'):
        fitted.predict(sample[:1])


def test_heldout_words_and_extreme_features_never_refit_preprocessing():
    training = rows(2020)+rows(2021)
    model = m.Regressor(True, .1).fit(training, '2021-12-31')
    heldout = rows(2022, 2)+rows(2023, 1)
    for r in heldout:
        r['current_text'] = 'quasarfuturetoken ' * 100
        r['features'].update(metric=1e9, scope='never_seen_category')
    state = (deepcopy(model.vocabulary.vocabulary_), model.vocabulary.idf_.copy(),
             model.imputer.statistics_.copy(), model.scaler.mean_.copy(),
             model.scaler.scale_.copy(), model.selected.copy(), model.estimator.coef_.copy())
    answer = model.predict(heldout)
    assert np.isfinite(answer).all()
    assert 'quasarfuturetoken' not in model.vocabulary.vocabulary_
    assert not any('never_seen_category' in x for x in model.names)
    assert state[0] == model.vocabulary.vocabulary_
    for before, after in zip(state[1:], (model.vocabulary.idf_, model.imputer.statistics_,
                                        model.scaler.mean_, model.scaler.scale_,
                                        model.selected, model.estimator.coef_)):
        np.testing.assert_array_equal(before, after)
    j = model.names.index('metric')
    assert model.imputer.statistics_[j] == np.median([r['features']['metric'] for r in training
                                                     if r['features']['metric'] is not None])
    altered = deepcopy(heldout)
    for r in altered: r['target_pp'] = -1e12
    np.testing.assert_array_equal(answer, model.predict(altered))


def test_future_targets_must_be_masked_before_selection():
    allrows = rows(2020, 200)+rows(2021, 100)+rows(2022, 1)
    with pytest.raises(ValueError, match='Evaluation targets must remain masked'):
        m.select_and_refit(allrows)


def test_each_model_selects_own_alpha_only_on_2021_and_final_refit_includes_late2020(monkeypatch):
    calls = []
    class SpyRegressor:
        def __init__(self, use_text, alpha):
            self.use_text, self.alpha = use_text, alpha
        def fit(self, sample, cutoff):
            self.training_event_ids = tuple(r['event_id'] for r in sample)
            calls.append(('fit', self.use_text, self.alpha, cutoff, self.training_event_ids))
            return self
        def predict(self, sample):
            assert {r['entry_date'][:4] for r in sample} == {'2021'}
            # Independent chosen penalty: numeric .1, text .01.
            optimum = .01 if self.use_text else .1
            return np.array([r['target_pp'] for r in sample])+abs(self.alpha-optimum)
        def summary(self):
            return {'alpha': self.alpha}
    monkeypatch.setattr(m, 'Regressor', SpyRegressor)
    allrows = rows(2020, 200)+rows(2021, 100)
    late = deepcopy(allrows[0]); late.update(event_id='late2020', entry_date='2020-12-21', exit_date='2021-01-20')
    future = rows(2022, 1)[0]; future.update(target_pp=None, current_text='heldoutfutureonly')
    models, report = m.select_and_refit(allrows+[late, future])
    assert models['numeric'].alpha == .1 and models['text'].alpha == .01
    assert all('late2020' not in ids for _,_,_,cutoff,ids in calls if cutoff == '2020-12-31')
    assert all('late2020' in ids for _,_,_,cutoff,ids in calls if cutoff == '2021-12-31')
    assert all('2022:0' not in ids for _,_,_,_,ids in calls)


def test_missing_numeric_key_cannot_silently_become_observed_zero():
    model = m.Regressor(False, .1).fit(rows(), '2020-12-31')
    explicit = rows(2021, 1)[0]; explicit['features']['metric'] = None
    omitted = deepcopy(explicit); del omitted['features']['metric']
    # Either reject malformed feature schema or interpret omission exactly as missing.
    try:
        actual = model.predict([omitted])
    except ValueError:
        return
    np.testing.assert_allclose(actual, model.predict([explicit]), rtol=0, atol=1e-12)
