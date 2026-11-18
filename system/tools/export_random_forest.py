"""Rebuild and export the original five-class Stage 2 RF from the original feature CSV.

Expected source: collector/data/ml_ready/rf_all_train.csv, rf_P13_test.csv,
rf_feature_manifest.json and (optionally) rf_predictions.csv.
Use only trusted feature tables. This exports a freshly fitted equivalent, NOT the
unavailable original pickled model. Test CSV is never passed to fit().
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import make_pipeline


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True, help='Original collector/data/ml_ready folder')
    p.add_argument('--output', type=Path, default=Path('models/random_forest/v1/classifier.joblib'))
    p.add_argument('--report', type=Path, default=None)
    args = p.parse_args()
    source = args.source
    train = pd.read_csv(source / 'rf_all_train.csv')
    test = pd.read_csv(source / 'rf_P13_test.csv')
    schema = json.loads((source/'rf_feature_manifest.json').read_text())
    cols = schema['feature_columns']
    for frame, name in [(train, 'train'), (test, 'test')]:
        if list(frame.columns) != cols+['model_key']:
            raise ValueError(f'{name} feature columns/order differ from the manifest')
    xtrain, ytrain = train[cols], train['model_key']
    xtest, ytest = test[cols], test['model_key']
    classifier = make_pipeline(
        SimpleImputer(strategy='median'),
        RandomForestClassifier(n_estimators=500, class_weight='balanced', random_state=42, n_jobs=-1))
    classifier.fit(xtrain, ytrain)
    pred = classifier.predict(xtest)
    report = {'source': 'reconstructed_from_original_feature_tables',
              'sklearn_version': sklearn.__version__,
              'seed': 42, 'estimators': 500, 'train_rows': len(train), 'test_rows': len(test),
              'feature_count': len(cols), 'classes': list(classifier.classes_),
              'heldout_accuracy': accuracy_score(ytest, pred),
              'heldout_macro_f1': f1_score(ytest, pred, average='macro'),
              'original_predictions_match': None,
              'original_train_sha256': hashlib.sha256((source/'rf_all_train.csv').read_bytes()).hexdigest()}
    historic = source/'rf_predictions.csv'
    if historic.exists():
        old = pd.read_csv(historic)
        old = old[old['experiment']=='all_personas'].sort_values('test_row')
        if len(old) != len(pred):
            raise ValueError('Original prediction count differs')
        report['original_predictions_match'] = int(sum(old['predicted_model_key'].to_numpy() == pred))
        report['original_predictions_total'] = int(len(pred))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(classifier, args.output, compress=3)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
