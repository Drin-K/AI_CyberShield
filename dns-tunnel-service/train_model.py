# train_model.py
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

def synthetic_dataset(n=3000, seed=42):
    rng = np.random.RandomState(seed)
    X = []
    y = []
    for i in range(n):
        if rng.rand() < 0.7:
            chunk_count = int(max(1, rng.poisson(2)))
            avg_chunk_size = abs(rng.normal(300, 50))
            std_chunk_size = abs(rng.normal(20, 10))
            total_bytes = chunk_count * avg_chunk_size
            interarrival_mean = max(0.01, rng.normal(1.0, 0.5))
            duration = max(0.01, rng.normal(3.0, 2.0))
            entropy = rng.normal(3.2, 0.6)
            printable_ratio = rng.normal(0.85, 0.08)
            label = 0
        else:
            chunk_count = int(max(1, rng.poisson(8)))
            avg_chunk_size = abs(rng.normal(80, 30))
            std_chunk_size = abs(rng.normal(5, 4))
            total_bytes = chunk_count * avg_chunk_size
            interarrival_mean = max(0.001, rng.normal(0.2, 0.1))
            duration = max(0.01, rng.normal(2.0, 1.0))
            entropy = rng.normal(4.6, 0.4)
            printable_ratio = rng.normal(0.30, 0.2)
            label = 1

        X.append([
            chunk_count,
            avg_chunk_size,
            std_chunk_size,
            total_bytes,
            interarrival_mean,
            duration,
            entropy,
            printable_ratio
        ])
        y.append(label)
    return np.array(X), np.array(y)

def main():
    X, y = synthetic_dataset(3000)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=1, stratify=y)
    clf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=1)
    clf.fit(X_train, y_train)
    preds = clf.predict(X_test)
    print(classification_report(y_test, preds))
    joblib.dump(clf, "model.pkl")
    print("Saved model to model.pkl")

if __name__ == "__main__":
    main()
