import logging
import json
import sys
import os

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from flask import Flask, request, jsonify, render_template_string
import requests
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
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
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
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
            max-width: 500px;
            width: 100%;
            animation: slideUp 0.5s ease-out;
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .success-icon {
            font-size: 5rem;
            color: #4CAF50;
            margin-bottom: 20px;
            animation: bounceIn 0.8s ease-out;
        }
        @keyframes bounceIn {
            0%, 20%, 40%, 60%, 80% { transform: translateY(0); }
            40% { transform: translateY(-20px); }
            60% { transform: translateY(-10px); }
        }
        h1 {
            color: #2E7D32;
            margin-bottom: 15px;
            font-size: 2.2rem;
            font-weight: 600;
        }
        .amount {
            font-size: 1.8rem;
            color: #4CAF50;
            font-weight: bold;
            margin: 20px 0;
        }
        p {
            color: #666;
            line-height: 1.6;
            margin-bottom: 30px;
            font-size: 1.1rem;
        }
        .features-list {
            background: #f8fffe;
            border-left: 4px solid #4CAF50;
            padding: 20px;
            margin: 25px 0;
            text-align: left;
            border-radius: 8px;
        }
        .features-list h3 {
            color: #2E7D32;
            margin: 0 0 15px 0;
            font-size: 1.2rem;
        }
        .features-list ul {
            margin: 0;
            padding-left: 20px;
            color: #555;
        }
        .features-list li {
            margin: 8px 0;
            line-height: 1.5;
        }
        .btn {
            background: #4CAF50;
            color: white;
            padding: 18px 40px;
            border: none;
            border-radius: 50px;
            font-size: 1.2rem;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s ease;
            margin: 20px 0;
            font-weight: 600;
            box-shadow: 0 4px 15px rgba(76, 175, 80, 0.3);
        }
        .btn:hover {
            background: #45a049;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(76, 175, 80, 0.4);
        }
        .notification-info {
            margin-top: 30px;
            padding: 20px;
            background: #e8f5e8;
            border-radius: 12px;
            color: #2e7d32;
            font-size: 1rem;
        }
        .redirect-timer {
            color: #888;
            font-size: 0.9rem;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✅</div>
        <h1>Payment Successful!</h1>
        <div class="amount">${{ amount }}</div>
        <p>Thank you! Your premium subscription has been activated successfully.</p>
        
        <div class="features-list">
            <h3>🎉 Premium Features Now Active:</h3>
            <ul>
                <li>✨ Unlimited reminders</li>
                <li>🔔 Priority notifications</li>
                <li>📅 Advanced scheduling</li>
                <li>👑 Premium badge</li>
                <li>🎯 Enhanced AI features</li>
            </ul>
        </div>
        
        <div class="notification-info">
            <strong>📱 Check your Telegram!</strong><br>
            A confirmation message has been sent to your bot.
        </div>
        
        <a href="https://t.me/ai_reminderbot" class="btn">🤖 Return to Bot</a>
        
        <div class="redirect-timer">
            Auto-redirecting to bot in <span id="countdown">8</span> seconds...
        </div>
    </div>
    
    <script>
        // Countdown timer
        let countdown = 8;
        const timer = setInterval(() => {
            countdown--;
            document.getElementById('countdown').textContent = countdown;
            if (countdown <= 0) {
                clearInterval(timer);
                window.location.href = "https://t.me/ai_reminderbot";
            }
        }, 1000);
        
        // Send verification request immediately
        fetch('/verify_payment?session_id={{ session_id }}', {method: 'POST'})
            .then(response => response.json())
            .then(data => console.log('Payment verified:', data))
            .catch(error => console.log('Verification error:', error));
    </script>
</body>
</html>
"""

FAILED_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Failed</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #f44336 0%, #d32f2f 100%);
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
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
            max-width: 500px;
            width: 100%;
            animation: slideUp 0.5s ease-out;
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .failed-icon {
            font-size: 5rem;
            color: #f44336;
            margin-bottom: 20px;
        }
        h1 {
            color: #d32f2f;
            margin-bottom: 15px;
            font-size: 2.2rem;
            font-weight: 600;
        }
        p {
            color: #666;
            line-height: 1.6;
            margin-bottom: 25px;
            font-size: 1.1rem;
        }
        .error-info {
            background: #ffebee;
            border-left: 4px solid #f44336;
            padding: 20px;
            margin: 25px 0;
            text-align: left;
            border-radius: 8px;
            color: #c62828;
        }
        .btn {
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 50px;
            font-size: 1.1rem;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s ease;
            margin: 10px;
            font-weight: 600;
        }
        .btn-primary {
            background: #2196F3;
            box-shadow: 0 4px 15px rgba(33, 150, 243, 0.3);
        }
        .btn-primary:hover {
            background: #1976D2;
            transform: translateY(-2px);
        }
        .btn-secondary {
            background: #6c757d;
            box-shadow: 0 4px 15px rgba(108, 117, 125, 0.3);
        }
        .btn-secondary:hover {
            background: #545b62;
            transform: translateY(-2px);
        }
        .redirect-timer {
            color: #888;
            font-size: 0.9rem;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="failed-icon">❌</div>
        <h1>Payment Failed</h1>
        <p>Unfortunately, your payment could not be processed at this time.</p>
        
        <div class="error-info">
            <strong>What happened?</strong><br>
            • Payment was declined by your bank<br>
            • Insufficient funds or card limits<br>
            • Network connectivity issues<br>
            • Temporary payment processor error
        </div>
        
        <p>Don't worry! No charges were made to your account. You can try again with a different payment method or contact your bank if the issue persists.</p>
        
        <a href="https://t.me/ai_reminderbot?start=try_premium_again" class="btn btn-primary">🔄 Try Again</a>
        <a href="https://t.me/ai_reminderbot" class="btn btn-secondary">🤖 Return to Bot</a>
        
        <div class="redirect-timer">
            Auto-redirecting to bot in <span id="countdown">10</span> seconds...
        </div>
    </div>
    
    <script>
        // Countdown timer
        let countdown = 10;
        const timer = setInterval(() => {
            countdown--;
            document.getElementById('countdown').textContent = countdown;
            if (countdown <= 0) {
                clearInterval(timer);
                window.location.href = "https://t.me/ai_reminderbot";
            }
        }, 1000);
        
        // Send failed payment notification
        fetch('/notify_payment_failed?session_id={{ session_id }}', {method: 'POST'})
            .then(response => response.json())
            .then(data => console.log('Failed payment notification sent:', data))
            .catch(error => console.log('Notification error:', error));
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
            background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%);
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
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
            max-width: 500px;
            width: 100%;
            animation: slideUp 0.5s ease-out;
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .cancel-icon {
            font-size: 5rem;
            color: #ff9800;
            margin-bottom: 20px;
        }
        h1 {
            color: #e65100;
            margin-bottom: 15px;
            font-size: 2.2rem;
            font-weight: 600;
        }
        p {
            color: #666;
            line-height: 1.6;
            margin-bottom: 25px;
            font-size: 1.1rem;
        }
        .btn {
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 50px;
            font-size: 1.1rem;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s ease;
            margin: 10px;
            font-weight: 600;
        }
        .btn-primary {
            background: #2196F3;
            box-shadow: 0 4px 15px rgba(33, 150, 243, 0.3);
        }
        .btn-primary:hover {
            background: #1976D2;
            transform: translateY(-2px);
        }
        .btn-secondary {
            background: #6c757d;
            box-shadow: 0 4px 15px rgba(108, 117, 125, 0.3);
        }
        .btn-secondary:hover {
            background: #545b62;
            transform: translateY(-2px);
        }
        .redirect-timer {
            color: #888;
            font-size: 0.9rem;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="cancel-icon">⚠️</div>
        <h1>Payment Cancelled</h1>
        <p>No worries! Your payment was cancelled and no charges were made.</p>
        <p>You can try again anytime or continue using the free features of our bot.</p>
        
        <a href="https://t.me/ai_reminderbot?start=try_premium_again" class="btn btn-primary">🔄 Try Premium Again</a>
        <a href="https://t.me/ai_reminderbot" class="btn btn-secondary">🤖 Return to Bot</a>
        
        <div class="redirect-timer">
            Auto-redirecting to bot in <span id="countdown">8</span> seconds...
        </div>
    </div>
    
    <script>
        // Countdown timer
        let countdown = 8;
        const timer = setInterval(() => {
            countdown--;
            document.getElementById('countdown').textContent = countdown;
            if (countdown <= 0) {
                clearInterval(timer);
                window.location.href = "https://t.me/ai_reminderbot";
            }
        }, 1000);
        
        // Send cancel notification
        fetch('/notify_payment_cancelled', {method: 'POST'})
            .then(response => response.json())
            .then(data => console.log('Cancel notification sent:', data))
            .catch(error => console.log('Notification error:', error));
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
        
        # Get payment amount for display
        amount = "9.99"  # Default amount
        try:
            from src.database import get_db
            from src.models import Payment
            db = next(get_db())
            payment = db.query(Payment).filter(Payment.track_id == session_id).first()
            if payment:
                amount = f"{payment.amount/100:.2f}"
            db.close()
        except Exception as e:
            logger.error(f"Error getting payment amount: {e}")
        
        # Verify payment and send Telegram notification
        try:
            verify_payment_and_notify(session_id)
        except Exception as e:
            logger.error(f"Error in payment verification/notification: {e}")
        
        return render_template_string(SUCCESS_PAGE_HTML, session_id=session_id, amount=amount)
    else:
        return render_template_string(SUCCESS_PAGE_HTML, session_id="Unknown", amount="9.99"), 400

@app.route('/payment_failed', methods=['GET'])
def payment_failed():
    """
    Handle failed payment redirect with proper HTML page
    """
    session_id = request.args.get('session_id', 'unknown')
    logger.info(f"Payment failed redirect for session: {session_id}")
    
    # Send failed payment notification immediately
    try:
        notify_payment_failed(session_id)
    except Exception as e:
        logger.error(f"Error in failed payment notification: {e}")
    
    return render_template_string(FAILED_PAGE_HTML, session_id=session_id)

@app.route('/payment_cancel', methods=['GET'])
def payment_cancel():
    """
    Handle cancelled payment redirect with proper HTML page
    """
    logger.info("Payment cancelled by user")
    
    # Send cancel notification immediately
    try:
        notify_payment_cancelled()
    except Exception as e:
        logger.error(f"Error in cancel payment notification: {e}")
    
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

@app.route('/notify_payment_failed', methods=['POST'])
def notify_payment_failed_endpoint():
    """
    Send failed payment notification to user
    """
    session_id = request.args.get('session_id', 'unknown')
    try:
        result = notify_payment_failed(session_id)
        return jsonify({"success": True, "message": "Failed payment notification sent"})
    except Exception as e:
        logger.error(f"Error sending failed payment notification: {e}")
        return jsonify({"error": "Notification failed"}), 500

@app.route('/notify_payment_cancelled', methods=['POST'])
def notify_payment_cancelled_endpoint():
    """
    Send cancelled payment notification to user
    """
    try:
        result = notify_payment_cancelled()
        return jsonify({"success": True, "message": "Cancel payment notification sent"})
    except Exception as e:
        logger.error(f"Error sending cancel payment notification: {e}")
        return jsonify({"error": "Notification failed"}), 500

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

• ✨ Unlimited reminders
• 🔔 Priority notifications  
• 📅 Advanced scheduling
• 👑 Premium badge
• 🎯 Enhanced AI features

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
            return True
        else:
            logger.error(f"Failed to send Telegram notification: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exception sending Telegram notification: {e}")
        return False

def notify_payment_failed(session_id: str):
    """
    Send notification for failed payment
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured")
        return False
    
    # Try to get user info from session
    chat_id = None
    try:
        from src.database import get_db
        from src.models import Payment, User
        db = next(get_db())
        payment = db.query(Payment).filter(Payment.track_id == session_id).first()
        if payment:
            user = db.query(User).filter(User.id == payment.user_id).first()
            if user:
                chat_id = user.chat_id
        db.close()
    except Exception as e:
        logger.error(f"Error getting user info for failed payment notification: {e}")
    
    if not chat_id:
        logger.warning(f"Could not find chat_id for failed payment session {session_id}")
        return False
    
    message = f"""❌ **Payment Failed**

Unfortunately, your premium subscription payment could not be processed.

🔍 **Common reasons:**
• Payment declined by bank
• Insufficient funds 
• Network connectivity issues
• Temporary payment processor error

💡 **What to do:**
• Try again with a different payment method
• Contact your bank if the issue persists
• No charges were made to your account

Click "Upgrade to Premium" to try again whenever you're ready! 🚀"""

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            logger.info(f"Successfully sent failed payment notification for session {session_id}")
            return True
        else:
            logger.error(f"Failed to send failed payment notification: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exception sending failed payment notification: {e}")
        return False

def notify_payment_cancelled():
    """
    Send notification for cancelled payment
    """
    # For cancelled payments, we don't have session info, so we'll log it
    # In a real implementation, you might want to track this differently
    logger.info("Payment cancelled by user - no specific notification sent")
    return True

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # Only run if this file is executed directly
    app.run(host='0.0.0.0', port=5000, debug=True) 