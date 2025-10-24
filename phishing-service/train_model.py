# train_model.py
"""
Train TF-IDF + LogisticRegression model using subject, body, sender.
Input: emails_labeled.csv with columns: subject, body, sender, label (0/1)
Output: phish_model.joblib containing tfidf, scaler, clf, meta (free_domains)
"""
import re
import math
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from scipy.sparse import hstack
from sklearn.metrics import classification_report, roc_auc_score

# ------------- helper functions -------------
def extract_links(text):
    if not isinstance(text, str):
        return []
    return re.findall(r"https?://[^\s)\"'>]+", text)

def host_entropy_from_url(url):
    try:
        from urllib.parse import urlparse
        h = urlparse(url).hostname or ""
        if not h:
            return 0.0
        counts = {}
        for c in h:
            counts[c] = counts.get(c, 0) + 1
        probs = [v/len(h) for v in counts.values()]
        ent = -sum(p * math.log(p, 2) for p in probs)
        return ent
    except Exception:
        return 0.0

def sender_domain(email_or_domain):
    if not isinstance(email_or_domain, str) or email_or_domain.strip() == "":
        return ""
    # if contains '@', return part after @, else treat as domain
    if "@" in email_or_domain:
        return email_or_domain.split("@")[-1].lower().strip()
    return email_or_domain.lower().strip()

FREE_EMAIL_DOMAINS = {
    "gmail.com","yahoo.com","hotmail.com","outlook.com","icloud.com","aol.com","protonmail.com"
}

def extract_sender_features(sender):
    d = sender_domain(sender)
    features = {}
    features['sender_domain_len'] = len(d)
    features['sender_has_digits'] = int(bool(re.search(r'\d', d)))
    features['sender_is_free'] = int(d in FREE_EMAIL_DOMAINS)
    # suspicious TLD/simple signal
    features['sender_tld_dot'] = d.split('.')[-1] if d else ''
    features['sender_tld_unusual'] = int(d.endswith(('.tk','.xyz','.top','.club','.info')) or d.endswith('.ru'))
    return features

def make_features(df):
    df = df.copy()
    df['subject'] = df['subject'].fillna('').astype(str)
    df['body'] = df['body'].fillna('').astype(str)
    df['sender'] = df['sender'].fillna('').astype(str)
    df['text'] = (df['subject'] + ' ' + df['body']).str.lower()

    # numeric body features
    df['num_links'] = df['body'].apply(lambda t: len(extract_links(t)))
    df['has_login_token'] = df['body'].str.contains(r'\b(verify|confirm|login|password|secure)\b', na=False, flags=re.I).astype(int)
    df['first_link_entropy'] = df['body'].apply(lambda t: host_entropy_from_url(extract_links(t)[0]) if extract_links(t) else 0.0)

    # sender features
    sfeatures = df['sender'].apply(extract_sender_features)
    df['sender_domain_len'] = sfeatures.apply(lambda x: x['sender_domain_len'])
    df['sender_has_digits'] = sfeatures.apply(lambda x: x['sender_has_digits'])
    df['sender_is_free'] = sfeatures.apply(lambda x: x['sender_is_free'])
    df['sender_tld_unusual'] = sfeatures.apply(lambda x: x['sender_tld_unusual'])

    return df

# ------------- load dataset -------------
print("Loading emails_labeled.csv ...")
df = pd.read_csv("emails_labeled.csv")  # ensure this file exists
df = make_features(df)
print("Total rows:", len(df))

# features and target
X_text = df['text'].values
X_num = df[['num_links','has_login_token','first_link_entropy',
            'sender_domain_len','sender_has_digits','sender_is_free','sender_tld_unusual']].values
y = df['label'].astype(int).values

# split
X_text_train, X_text_test, X_num_train, X_num_test, y_train, y_test = train_test_split(
    X_text, X_num, y, test_size=0.2, random_state=42, stratify=y)

# vectorize text
print("Fitting TF-IDF...")
tfidf = TfidfVectorizer(ngram_range=(1,2), max_features=20000, stop_words='english')
X_tfidf_train = tfidf.fit_transform(X_text_train)
X_tfidf_test = tfidf.transform(X_text_test)

# scale numeric features
print("Scaling numeric features...")
scaler = StandardScaler()
X_num_train_scaled = scaler.fit_transform(X_num_train)
X_num_test_scaled = scaler.transform(X_num_test)

# combine
X_train = hstack([X_tfidf_train, X_num_train_scaled])
X_test = hstack([X_tfidf_test, X_num_test_scaled])

# train classifier
print("Training classifier (LogisticRegression)...")
clf = LogisticRegression(max_iter=2000, class_weight='balanced')
clf.fit(X_train, y_train)

# evaluate
y_pred = clf.predict(X_test)
y_proba = clf.predict_proba(X_test)[:,1]
print("\nClassification report:\n", classification_report(y_test, y_pred))
print("ROC AUC:", roc_auc_score(y_test, y_proba))

# save artifacts
print("Saving phish_model.joblib ...")
joblib.dump({
    "tfidf": tfidf,
    "scaler": scaler,
    "clf": clf,
    "meta": {
        "free_domains": list(FREE_EMAIL_DOMAINS)
    }
}, "phish_model.joblib")
print("Saved phish_model.joblib")
