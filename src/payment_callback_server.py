import logging
import json
import sys
import os

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from flask import Flask, request, jsonify
from src.payment import handle_stripe_webhook
from config.config import settings

logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """
    Handle Stripe webhook events
    """
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    if not sig_header:
        logger.error("No Stripe signature header found")
        return jsonify({"error": "No signature header"}), 400
    
    try:
        result = handle_stripe_webhook(payload, sig_header)
        
        if result["success"]:
            logger.info(f"Webhook processed successfully: {result['message']}")
            return jsonify({"status": "success"}), 200
        else:
            logger.error(f"Webhook processing failed: {result['message']}")
            return jsonify({"error": result["message"]}), 400
            
    except Exception as e:
        logger.error(f"Exception in webhook handler: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/payment_success', methods=['GET'])
def payment_success():
    """
    Handle successful payment redirect
    """
    session_id = request.args.get('session_id')
    if session_id:
        logger.info(f"Payment success redirect for session: {session_id}")
        return jsonify({
            "status": "success",
            "message": "Payment completed successfully",
            "session_id": session_id
        })
    else:
        return jsonify({"error": "No session ID provided"}), 400

@app.route('/payment_cancel', methods=['GET'])
def payment_cancel():
    """
    Handle cancelled payment redirect
    """
    logger.info("Payment cancelled by user")
    return jsonify({
        "status": "cancelled",
        "message": "Payment was cancelled"
    })

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # Only run if this file is executed directly
    app.run(host='0.0.0.0', port=5000, debug=True) 