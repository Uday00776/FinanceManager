import os
import random
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from django.core.management.base import BaseCommand
from django.conf import settings
from chitfund.models import Client, MonthlyPayment
from chitfund.ml.risk_predictor import extract_features, ML_DIR, MODEL_PATH

class Command(BaseCommand):
    help = 'Trains the Risk Predictor ML model using client data.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Gathering data for ML model...")
        
        data = []
        labels = []
        
        clients = Client.objects.all()
        # If there are actual clients, use them as base for actual data
        for client in clients:
            features = extract_features(client.id)
            data.append(features)
            # Bootstrapping a label based on historical heuristics for training data
            if features["total_unpaid"] * 2 + features["average_days_late"] > 10:
                labels.append(1) # High Risk/Default
            else:
                labels.append(0) # Low Risk

        # Generate synthetic data to ensure the model has enough variance to train on
        # This is purely because portfolio/development databases usually lack enough
        # samples to train a meaningful ML classifier.
        self.stdout.write("Generating synthetic data for robust training...")
        for _ in range(500):
            # Healthy user profile
            if random.random() > 0.4:
                months_joined = random.randint(1, 48)
                total_paid = random.randint(1, months_joined)
                data.append({
                    "months_joined": months_joined,
                    "total_paid": total_paid,
                    "total_unpaid": random.randint(0, 1),
                    "average_days_late": random.uniform(0, 3),
                    "lifted_status_binary": random.choice([0, 1])
                })
                labels.append(0)
            else:
                # Risky user profile
                months_joined = random.randint(3, 48)
                data.append({
                    "months_joined": months_joined,
                    "total_paid": random.randint(0, max(1, months_joined - 2)),
                    "total_unpaid": random.randint(2, 8),
                    "average_days_late": random.uniform(5, 45),
                    "lifted_status_binary": random.choice([0, 1])
                })
                labels.append(1)

        df = pd.DataFrame(data)
        y = pd.Series(labels)

        self.stdout.write(f"Training RandomForestClassifier on {len(df)} samples...")
        model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
        model.fit(df, y)

        if not os.path.exists(ML_DIR):
            os.makedirs(ML_DIR)

        joblib.dump(model, MODEL_PATH)

        self.stdout.write("--- Feature Importances ---")
        importances = model.feature_importances_
        for name, importance in zip(df.columns, importances):
            self.stdout.write(f"  {name}: {importance:.4f}")

        self.stdout.write(self.style.SUCCESS(f'Successfully trained and saved AI Context Model to {MODEL_PATH}'))
