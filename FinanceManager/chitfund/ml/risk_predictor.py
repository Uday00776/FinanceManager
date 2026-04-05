import os
import joblib
import pandas as pd
from django.utils import timezone
from django.conf import settings
from chitfund.models import Client, MonthlyPayment

# Ensure the ML models directory exists
ML_DIR = os.path.join(settings.BASE_DIR, "chitfund", "ml", "models")
MODEL_PATH = os.path.join(ML_DIR, "risk_model.joblib")

def extract_features(client_id):
    """
    Extracts numerical features for a client to be fed into the ML model.
    """
    client = Client.objects.get(id=client_id)
    
    # Feature 1: Months since joined
    today = timezone.localdate()
    months_joined = (today.year - client.joined_date.year) * 12 + (today.month - client.joined_date.month)
    months_joined = max(1, months_joined) # Avoid 0 length representing immediate
    
    payments = client.payments.all()
    
    # Feature 2 & 3: Paid and Unpaid counts
    total_paid = payments.filter(status=MonthlyPayment.PaymentStatus.PAID).count()
    total_unpaid = payments.filter(status=MonthlyPayment.PaymentStatus.UNPAID).count()
    
    # Feature 4: Average days late
    paid_payments = payments.filter(status=MonthlyPayment.PaymentStatus.PAID, paid_date__isnull=False)
    total_delay = sum(
        max(0, (p.paid_date - p.month).days) for p in paid_payments
    )
    average_days_late = total_delay / max(1, total_paid)
    
    # Feature 5: Lifted status (1 if lifted, 0 if not)
    # The hypothesis is that after a client lifts the pot, there's inherently a change in risk dynamic.
    lifted_status_binary = 1 if client.status == Client.LiftStatus.LIFTED else 0
    
    return {
        "months_joined": months_joined,
        "total_paid": total_paid,
        "total_unpaid": total_unpaid,
        "average_days_late": average_days_late,
        "lifted_status_binary": lifted_status_binary,
    }

class RiskPredictor:
    def __init__(self):
        self.model = None
        try:
            if os.path.exists(MODEL_PATH):
                self.model = joblib.load(MODEL_PATH)
        except Exception as e:
            print(f"Warning: Could not load the ML model: {e}")
            
    def predict_risk(self, client_id):
        """
        Returns a dictionary with status, score, and context features.
        """
        features_dict = extract_features(client_id)
        
        # If no model is trained yet, fallback to a heuristic
        if self.model is None:
            score = self._heuristic_score(features_dict)
            source = "heuristic"
        else:
            # Predict using model
            df = pd.DataFrame([features_dict])
            # The model predicts the probability of defaulting/unpaid
            probabilities = self.model.predict_proba(df)[0]
            # Assumes class 1 is "High Risk / Default"
            score = probabilities[1] * 100
            source = "ml_model"
            
        risk_level = "Low"
        alert_color = "green"
        if score > 50:
            risk_level = "High"
            alert_color = "red"
        elif score > 25:
            risk_level = "Medium"
            alert_color = "yellow"
            
        return {
            "score": round(score, 1),
            "level": risk_level,
            "color": alert_color,
            "source": source,
            "features": features_dict
        }
        
    def _heuristic_score(self, features):
        """Fallback rule-based scoring if the ML Model hasn't been trained."""
        # Simple heuristic mapping raw numbers to a 0-100 score
        if features["months_joined"] < 2 and features["total_unpaid"] > 0:
            return 80.0
        
        score = (features["total_unpaid"] * 30) + (features["average_days_late"] * 1.5)
        # Being lifted increases risk slightly if they have bad history
        if features["total_unpaid"] > 0 and features["lifted_status_binary"] == 1:
            score += 15
            
        return min(100.0, score)

# Singleton instance to be imported across the app
risk_predictor = RiskPredictor()
