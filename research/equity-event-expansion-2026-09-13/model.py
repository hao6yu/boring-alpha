"""Past-only numerical and earnings-language elastic-net comparison.

Rows contain event_id, cik, entry_date, exit_date, status, features (a flat
mapping of numeric values/None and categorical strings), current_text,
prior_text, and target_pp. READY describes information available before entry;
it must never depend on future price availability. A target may be unavailable.
The caller constructs matured targets only for the requested development slice.
No files, network, prices or models are accessed on import.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet
from sklearn.preprocessing import StandardScaler

POLICY_SHA = '5c9daa1573ead42077ea323e641433c69112d6d3977f5e20c91d8bd1d04513bc'


def policy():
    path = Path(__file__).with_name('experiment-policy.json')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != POLICY_SHA:
        raise ValueError('Frozen experiment policy changed')
    return json.loads(raw)


def feature_dict(row, schema=None):
    result = {}
    schema = schema or {k: ('category' if isinstance(v, str) else 'number') for k, v in row['features'].items()}
    for key, kind in schema.items():
        value = row['features'].get(key)
        if kind == 'category':
            if value is not None and not isinstance(value, str):
                raise ValueError('Categorical feature changed type')
            result[key] = value if value is not None else 'UNKNOWN'
        else:
            if isinstance(value, str):
                raise ValueError('Numeric feature changed type')
            missing = value is None or not np.isfinite(float(value))
            result[key] = np.nan if missing else float(value)
            result[key + ':missing'] = float(missing)
    return result


def matured(rows, year, cutoff):
    return [r for r in rows if r['status'] == 'READY'
            and r['entry_date'][:4] == str(year) and r['exit_date'] <= cutoff
            and r.get('target_pp') is not None and np.isfinite(float(r['target_pp']))]


@dataclass
class Regressor:
    use_text: bool
    alpha: float

    def fit(self, rows, cutoff):
        if not rows or any(r['exit_date'] > cutoff for r in rows):
            raise ValueError('Unmatured label supplied to fit')
        self.fit_cutoff = cutoff
        self.training_event_ids = tuple(r['event_id'] for r in rows)
        y = np.asarray([float(r['target_pp']) for r in rows])
        if not np.isfinite(y).all():
            raise ValueError('Non-finite training target')
        self.dictionary = DictVectorizer(sparse=False, sort=True)
        self.feature_schema = {}
        for key in sorted({k for r in rows for k in r['features']}):
            values = [r['features'].get(key) for r in rows if r['features'].get(key) is not None]
            if any(isinstance(v, str) for v in values) and not all(isinstance(v, str) for v in values):
                raise ValueError('Feature mixes numeric and categorical observations')
            self.feature_schema[key] = 'category' if values and isinstance(values[0], str) else 'number'
        base = self.dictionary.fit_transform([feature_dict(r, self.feature_schema) for r in rows])
        self.imputer = SimpleImputer(strategy='median', keep_empty_features=True)
        base = self.imputer.fit_transform(base)
        self.names = list(self.dictionary.get_feature_names_out())
        if self.use_text:
            self.vocabulary = TfidfVectorizer(stop_words='english', min_df=5,
                max_df=.90, max_features=2000, token_pattern=r'(?u)\b[a-zA-Z][a-zA-Z]+\b',
                lowercase=True, ngram_range=(1, 1))
            current = [r['current_text'] for r in rows]
            prior = [r['prior_text'] for r in rows]
            self.vocabulary.fit(current + prior)
            delta = (self.vocabulary.transform(current) - self.vocabulary.transform(prior)).toarray()
            terms = self.vocabulary.get_feature_names_out()
            xc = delta - delta.mean(axis=0)
            yc = y - y.mean()
            denominator = np.sqrt(np.sum(xc*xc, axis=0) * np.sum(yc*yc))
            correlation = np.divide(xc.T @ yc, denominator, out=np.zeros_like(denominator), where=denominator > 0)
            self.selected = np.asarray(sorted(range(len(terms)), key=lambda j: (-abs(correlation[j]), terms[j]))[:25])
            self.selected_terms = [str(terms[j]) for j in self.selected]
            base = np.column_stack([base, delta[:, self.selected]])
            self.names.extend('text_delta:' + t for t in self.selected_terms)
        else:
            self.selected_terms = []
        self.scaler = StandardScaler()
        x = self.scaler.fit_transform(base)
        self.estimator = ElasticNet(alpha=self.alpha, l1_ratio=.5, fit_intercept=True,
            max_iter=20000, tol=1e-6, selection='cyclic', random_state=0)
        with warnings.catch_warnings():
            warnings.simplefilter('error', ConvergenceWarning)
            self.estimator.fit(x, y)
        return self

    def predict(self, rows):
        if not rows:
            return np.empty(0)
        if any(r['entry_date'] <= self.fit_cutoff for r in rows):
            raise ValueError('Prediction date must follow the fitted information cutoff')
        base = self.imputer.transform(self.dictionary.transform([feature_dict(r, self.feature_schema) for r in rows]))
        if self.use_text:
            delta = (self.vocabulary.transform([r['current_text'] for r in rows])
                     - self.vocabulary.transform([r['prior_text'] for r in rows])).toarray()
            base = np.column_stack([base, delta[:, self.selected]])
        answer = self.estimator.predict(self.scaler.transform(base))
        if not np.isfinite(answer).all():
            raise ValueError('Non-finite prediction')
        return answer

    def summary(self):
        return {'alpha': self.alpha, 'uses_text': self.use_text,
                'fit_cutoff': self.fit_cutoff, 'training_events': len(self.training_event_ids),
                'training_event_ids_sha256': hashlib.sha256('\n'.join(self.training_event_ids).encode()).hexdigest(),
                'selected_terms': self.selected_terms, 'feature_names': self.names,
                'coefficients': self.estimator.coef_.tolist(),
                'intercept': float(self.estimator.intercept_), 'iterations': int(self.estimator.n_iter_)}


def select_and_refit(rows):
    """Use 2021 only to choose penalties, then freeze a 2020–2021 refit."""
    spec = policy()
    fit_rows = matured(rows, 2020, '2020-12-31')
    validation_rows = matured(rows, 2021, '2021-12-31')
    if len(fit_rows) < 200 or len(validation_rows) < 100:
        raise ValueError(f'Insufficient development observations: fit={len(fit_rows)}, validation={len(validation_rows)}')
    if any(r.get('target_pp') is not None and r['entry_date'] >= '2022-01-01' for r in rows):
        raise ValueError('Evaluation targets must remain masked during model selection')
    models, report = {}, {'policy_sha256': POLICY_SHA, 'fit_observations': len(fit_rows),
                          'validation_observations': len(validation_rows), 'models': {}}
    actual = np.asarray([r['target_pp'] for r in validation_rows], dtype=float)
    for name, use_text in [('numeric', False), ('text', True)]:
        trials = []
        for alpha in spec['alpha_grid']:
            fitted = Regressor(use_text=use_text, alpha=alpha).fit(fit_rows, '2020-12-31')
            predicted = fitted.predict(validation_rows)
            trials.append({'alpha': alpha, 'validation_mse': float(np.mean((predicted - actual)**2))})
        selected = min(trials, key=lambda r: (r['validation_mse'], -r['alpha']))['alpha']
        final_rows = matured(rows, 2020, '2021-12-31') + validation_rows
        final = Regressor(use_text=use_text, alpha=selected).fit(final_rows, '2021-12-31')
        models[name] = final
        report['models'][name] = {'trials': trials, 'frozen_model': final.summary()}
    return models, report
