import os
# Fix OpenBLAS memory allocation error by limiting threads
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

from flask import Flask, request, jsonify
import sys
import numpy as np

# Add the project root path to ensure proper import of gridfs_handler
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from gridfs_handler import ModelGridFSHandler

app = Flask(__name__)

# Initialize the GridFS Handler for database operations
db_handler = ModelGridFSHandler()

# Load the model and vectorizer from MongoDB GridFS on startup
MODEL_NAME = "baseline_logistic"
print(f"📥 Loading model '{MODEL_NAME}' from MongoDB GridFS...")
model_data = db_handler.load_latest_model(MODEL_NAME)

clf, vectorizer, labels = None, None, []

if model_data:
    # Handle both Dictionary or Tuple return types from gridfs_handler smoothly
    if isinstance(model_data, dict):
        clf = model_data.get("model")
        vectorizer = model_data.get("vectorizer")
        labels = model_data.get("labels", [])
    elif isinstance(model_data, (tuple, list)):
        clf = model_data[0] if len(model_data) > 0 else None
        vectorizer = model_data[1] if len(model_data) > 1 else None
        labels = model_data[2] if len(model_data) > 2 else []
    
    print("✨ Model and Vectorizer loaded successfully into memory!")
else:
    print("⚠️ Warning: Model not found in GridFS. Please train and save the model first.")

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint to check API status and model availability"""
    status = "Active" if clf is not None else "Model Not Loaded"
    return jsonify({
        "status": status,
        "model_name": MODEL_NAME,
        "labels_count": len(labels)
    })

@app.route('/predict', methods=['POST'])
def predict_disease():
    """
    Main inference endpoint:
    Receives symptoms or medical text from the user, predicts the condition, 
    and retrieves warnings and recommendations (RAG).
    """
    if clf is None or vectorizer is None:
        return jsonify({"error": "Model is not loaded in memory. Train the model first."}), 500
    
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Please provide 'text' in JSON body."}), 400
    
    user_input_text = data['text']
    
    # 1. Transform the text using the saved vectorizer
    input_tfidf = vectorizer.transform([user_input_text])
    
    # 2. Predict the expected condition
    predicted_condition = clf.predict(input_tfidf)[0]
    
    # Get prediction confidence if available in the classifier
    confidence = 0.0
    if hasattr(clf, "predict_proba"):
        probabilities = clf.predict_proba(input_tfidf)
        confidence = float(np.max(probabilities))

    # 3. RAG step (Retrieve condition details from MongoDB - Conditions Collection)
    condition_details = {}
    try:
        conditions_collection = db_handler.db["conditions"]
        record = conditions_collection.find_one({"Condition_name": predicted_condition})
        
        if record:
            condition_details = {
                "condition": record.get("Condition_name", predicted_condition),
                "symptoms": record.get("Symptoms", ""),
                "causes": record.get("Causes", ""),
                "warnings": record.get("Warnings", ""),
                "recommendations": record.get("Recommendations", "")
            }
        else:
            condition_details = {"condition": predicted_condition}
    except Exception as e:
        print(f"⚠️ Error fetching condition details from DB: {e}")
        condition_details = {"condition": predicted_condition}

    # 4. Return the response to the user
    return jsonify({
        "status": "success",
        "predicted_condition": predicted_condition,
        "confidence": round(confidence * 100, 2),
        "medical_details": condition_details
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)