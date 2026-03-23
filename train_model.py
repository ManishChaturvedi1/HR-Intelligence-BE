import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
import joblib
import os

DATASET_PATH = "data/WA_Fn-UseC_-HR-Employee-Attrition.csv"

def get_boolean(val):
    return 1 if val == 'Yes' else 0

def train():
    print(f"Loading dataset from {DATASET_PATH}...")
    if not os.path.exists(DATASET_PATH):
        print("Dataset not found. Please ensure it is in the data/ folder.")
        return

    df = pd.read_csv(DATASET_PATH)

    # Convert target variable
    df['attrition'] = df['Attrition'].apply(get_boolean)
    df['overtime'] = df['OverTime'].apply(get_boolean)
    
    # Selected features matching our SQL Models
    # Age, Gender, Department, JobRole, MonthlyIncome(salary), YearsAtCompany(years_at_company)
    # JobSatisfaction, WorkLifeBalance, OverTime(overtime_bool), PerformanceRating, YearsSinceLastPromotion
    
    # We rename columns to match our expected schema for the model
    features = [
        'Age', 'Gender', 'Department', 'JobRole', 'MonthlyIncome', 
        'YearsAtCompany', 'JobSatisfaction', 'WorkLifeBalance', 
        'overtime', 'PerformanceRating', 'YearsSinceLastPromotion'
    ]
    
    X = df[features]
    y = df['attrition']

    # Preprocessing pipelines
    numeric_features = [
        'Age', 'MonthlyIncome', 'YearsAtCompany', 'JobSatisfaction', 
        'WorkLifeBalance', 'overtime', 'PerformanceRating', 'YearsSinceLastPromotion'
    ]
    numeric_transformer = StandardScaler()

    categorical_features = ['Gender', 'Department', 'JobRole']
    categorical_transformer = OneHotEncoder(handle_unknown='ignore')

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('cat', categorical_transformer, categorical_features)
        ])

    rf = RandomForestClassifier(n_estimators=100, random_state=42)

    # Append classifier to preprocessing pipeline.
    # Now we have a full prediction pipeline.
    clf = Pipeline(steps=[('preprocessor', preprocessor),
                          ('classifier', rf)])

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("Training model...")
    clf.fit(X_train, y_train)
    
    accuracy = clf.score(X_test, y_test)
    print(f"Model accuracy on test set: {accuracy:.4f}")

    print("Saving model to model.pkl...")
    joblib.dump(clf, 'model.pkl')
    print("Done!")

if __name__ == "__main__":
    train()
