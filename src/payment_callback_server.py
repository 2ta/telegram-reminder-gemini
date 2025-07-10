import logging
import json
import sys
import os

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from flask import Flask, request, jsonify, render_template_string
from src.payment import handle_stripe_webhook, verify_payment
from config.config import settings

logger = logging.getLogger(__name__)

app = Flask(__name__)

# HTML templates for payment pages
SUCCESS_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Successful!</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            max-width: 500px;
            width: 100%;
        }
        .success-icon {
            font-size: 4rem;
            color: #4CAF50;
            margin-bottom: 20px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 2rem;
        }
        p {
            color: #666;
            line-height: 1.6;
            margin-bottom: 30px;
        }
        .btn {
            background: #0088cc;
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 50px;
            font-size: 1.1rem;
            text-decoration: none;
            display: inline-block;
            transition: background 0.3s;
            margin: 10px;
        }
        .btn:hover {
            background: #006699;
        }
        .session-info {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
            font-family: monospace;
            font-size: 0.9rem;
            color: #666;
        }
        .redirect-info {
            margin-top: 30px;
            padding: 20px;
            background: #e8f5e8;
            border-radius: 10px;
            color: #2e7d32;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✅</div>
        <h1>Payment Successful!</h1>
        <p>Thank you! Your premium subscription has been activated successfully.</p>
        
        <div class="session-info">
            Session ID: {{ session_id }}
        </div>
        
        <div class="redirect-info">
            <strong>🤖 A confirmation message has been sent to your Telegram bot!</strong>
            <p>Return to the bot to start using your premium features.</p>
        </div>
        
        <a href="https://t.me/ai_reminderbot" class="btn">Return to Bot</a>
        <a href="https://t.me/ai_reminderbot?start=premium_activated" class="btn">Start Using Premium</a>
    </div>
    
    <script>
        // Auto-redirect after 10 seconds
        setTimeout(function() {
            window.location.href = "https://t.me/ai_reminderbot?start=premium_activated";
        }, 10000);
        
        // Send verification request immediately
        fetch('/verify_payment?session_id={{ session_id }}', {method: 'POST'})
            .then(response => response.json())
            .then(data => console.log('Payment verified:', data))
            .catch(error => console.log('Verification error:', error));
    </script>
</body>
</html>
"""

CANCEL_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Cancelled</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%);
            margin: 0;
            padding: 20px;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            max-width: 500px;
            width: 100%;
        }
        .cancel-icon {
            font-size: 4rem;
            color: #ff9800;
            margin-bottom: 20px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 2rem;
        }
        p {
            color: #666;
            line-height: 1.6;
            margin-bottom: 30px;
        }
        .btn {
            background: #0088cc;
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 50px;
            font-size: 1.1rem;
            text-decoration: none;
            display: inline-block;
            transition: background 0.3s;
            margin: 10px;
        }
        .btn:hover {
            background: #006699;
        }
        .btn-secondary {
            background: #6c757d;
        }
        .btn-secondary:hover {
            background: #545b62;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="cancel-icon">⚠️</div>
        <h1>Payment Cancelled</h1>
        <p>No worries! Your payment was cancelled and no charges were made.</p>
        <p>You can try again anytime or continue using the free features.</p>
        
        <a href="https://t.me/ai_reminderbot" class="btn">Return to Bot</a>
        <a href="https://t.me/ai_reminderbot?start=try_premium_again" class="btn btn-secondary">Try Premium Again</a>
    </div>
    
    <script>
        // Auto-redirect after 8 seconds
        setTimeout(function() {
            window.location.href = "https://t.me/ai_reminderbot";
        }, 8000);
    </script>
</body>
</html>
"""

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
    Handle successful payment redirect with proper HTML page
    """
    session_id = request.args.get('session_id')
    if session_id:
        logger.info(f"Payment success redirect for session: {session_id}")
        
        # Verify payment and send Telegram notification
        try:
            verify_payment_and_notify(session_id)
        except Exception as e:
            logger.error(f"Error in payment verification/notification: {e}")
        
        return render_template_string(SUCCESS_PAGE_HTML, session_id=session_id)
    else:
        return render_template_string(SUCCESS_PAGE_HTML, session_id="Unknown"), 400

@app.route('/payment_cancel', methods=['GET'])
def payment_cancel():
    """
    Handle cancelled payment redirect with proper HTML page
    """
    logger.info("Payment cancelled by user")
    return render_template_string(CANCEL_PAGE_HTML)

@app.route('/verify_payment', methods=['POST'])
def verify_payment_endpoint():
    """
    Verify payment and send notification to user
    """
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({"error": "No session ID provided"}), 400
    
    try:
        result = verify_payment_and_notify(session_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in payment verification: {e}")
        return jsonify({"error": "Verification failed"}), 500

def verify_payment_and_notify(session_id: str):
    """
    Verify payment and send Telegram notification to user
    """
    from src.payment import verify_payment
    from src.database import get_db
    from src.models import Payment, User
    import requests
    
    # Verify the payment
    verification_result = verify_payment(session_id)
    
    if verification_result['success']:
        # Get user information from payment
        db = next(get_db())
        try:
            payment = db.query(Payment).filter(Payment.track_id == session_id).first()
            if payment:
                user = db.query(User).filter(User.id == payment.user_id).first()
                if user:
                    # Send Telegram message to user
                    send_telegram_notification(user.telegram_id, user.chat_id, payment.amount)
                    logger.info(f"Sent premium activation notification to user {user.telegram_id}")
                    
        except Exception as e:
            logger.error(f"Error getting user info for notification: {e}")
        finally:
            db.close()
    
    return verification_result

def send_telegram_notification(user_id: int, chat_id: int, amount: int):
    """
    Send a Telegram message to notify user of successful payment
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured")
        return
    
    message = f"""🎉 **Premium Activated!**

✅ Payment successful: ${amount/100:.2f}
🚀 You now have unlimited reminders!
💎 Premium features unlocked:

• Create unlimited reminders
• Priority support
• Advanced scheduling options
• Premium badge

Start creating reminders now! 🎯

Type anything to create your first premium reminder or use /start to see your new premium status."""

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            logger.info(f"Successfully sent premium notification to user {user_id}")
        else:
            logger.error(f"Failed to send Telegram notification: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Exception sending Telegram notification: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # Only run if this file is executed directly
    app.run(host='0.0.0.0', port=5000, debug=True) 