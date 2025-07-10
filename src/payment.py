import logging
import json
import datetime
import stripe
from typing import Dict, Any, Optional, Tuple, Union

from src.database import get_db
from src.models import User, Payment, SubscriptionTier
from config.config import settings

logger = logging.getLogger(__name__)

# Configure Stripe
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY

# Default payment amount (in cents - $9.99)
DEFAULT_PAYMENT_AMOUNT = 999

class StripePaymentError(Exception):
    """Exception raised for errors in Stripe payment processing."""
    pass

class PaymentStatus:
    """Status codes for payment tracking"""
    PENDING = 1
    SUCCESS = 100
    FAILED = 102
    CANCELED = 201

def create_payment_link(user_id: int, chat_id: int, amount: int = DEFAULT_PAYMENT_AMOUNT) -> Tuple[bool, str, Optional[str]]:
    """
    Create a payment link using Stripe API
    
    Args:
        user_id: Telegram user ID
        chat_id: Telegram chat ID
        amount: Payment amount in cents
        
    Returns:
        (success, message, payment_url) tuple where:
        - success: Boolean indicating if operation was successful
        - message: Description message
        - payment_url: URL to redirect user to (if success is True)
    """
    if not settings.STRIPE_SECRET_KEY:
        return False, "Stripe is not configured", None
    
    try:
        # Create a Stripe checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Premium Subscription',
                        'description': f'Premium subscription for Telegram bot user {user_id}',
                    },
                    'unit_amount': amount,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{settings.PAYMENT_CALLBACK_URL_BASE}/payment_success?session_id={{CHECKOUT_SESSION_ID}}" if settings.PAYMENT_CALLBACK_URL_BASE else "https://example.com/success",
            cancel_url=f"{settings.PAYMENT_CALLBACK_URL_BASE}/payment_cancel" if settings.PAYMENT_CALLBACK_URL_BASE else "https://example.com/cancel",
            metadata={
                'user_id': str(user_id),
                'chat_id': str(chat_id),
                'telegram_user_id': str(user_id)
            }
        )
        
        # Save payment info to database
        db = next(get_db())
        try:
            # Get the database user ID from Telegram user ID
            from src.models import User
            user_db_obj = db.query(User).filter(User.telegram_id == user_id).first()
            if not user_db_obj:
                logger.error(f"User with telegram_id {user_id} not found in database when creating payment")
                return False, "User not found. Please start the bot first with /start", None
            
            # Create payment record using database user ID
            payment = Payment(
                user_id=user_db_obj.id,  # Use database user ID, not Telegram user ID
                chat_id=chat_id,
                track_id=session.id,  # Use Stripe session ID as track_id
                amount=amount,
                status=PaymentStatus.PENDING,
                created_at=datetime.datetime.now()
            )
            db.add(payment)
            db.commit()
            
            logger.info(f"Created Stripe payment link for telegram_user {user_id} (db_user {user_db_obj.id}) with session_id {session.id}")
            return True, "Payment link created successfully", session.url
            
        except Exception as e:
            db.rollback()
            logger.error(f"Database error when creating payment: {e}")
            return False, "Internal server error when recording payment", None
        finally:
            db.close()
            
    except stripe.error.StripeError as e:
        logger.error(f"Stripe payment creation failed: {e}")
        return False, f"Payment gateway error: {str(e)}", None
    except Exception as e:
        logger.error(f"Exception during payment link creation: {e}")
        return False, "Failed to connect to payment gateway", None

def verify_payment(session_id: str) -> Dict[str, Any]:
    """
    Verify a payment with Stripe
    
    Args:
        session_id: The Stripe session ID
        
    Returns:
        Dictionary with verification results including success status
    """
    if not settings.STRIPE_SECRET_KEY:
        return {
            "success": False,
            "message": "Stripe is not configured",
            "data": None
        }
    
    try:
        # Retrieve the session from Stripe
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Log verification details
        logger.info(f"Payment verification result for session_id {session_id}: {json.dumps(session.to_dict())}")
        
        # Check payment status
        if session.payment_status == 'paid':
            # Update payment status in database
            update_payment_status(session_id, PaymentStatus.SUCCESS, session.to_dict())
            return {
                "success": True,
                "message": "Payment verified successfully",
                "data": session.to_dict()
            }
        else:
            status = PaymentStatus.FAILED if session.payment_status == 'unpaid' else PaymentStatus.CANCELED
            update_payment_status(session_id, status, session.to_dict())
            return {
                "success": False,
                "message": f"Payment verification failed: {session.payment_status}",
                "data": session.to_dict()
            }
            
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error during payment verification: {e}")
        return {
            "success": False,
            "message": f"Error verifying payment: {str(e)}",
            "data": None
        }
    except Exception as e:
        logger.error(f"Exception during payment verification: {e}")
        return {
            "success": False,
            "message": f"Error verifying payment: {str(e)}",
            "data": None
        }

def update_payment_status(session_id: str, status: int, result_data: Dict[str, Any]) -> bool:
    """
    Update payment status in database
    
    Args:
        session_id: The Stripe session ID of the payment
        status: Status code
        result_data: Full response data from Stripe
        
    Returns:
        Boolean indicating if update was successful
    """
    db = next(get_db())
    try:
        payment = db.query(Payment).filter(Payment.track_id == session_id).first()
        
        if not payment:
            logger.error(f"Payment with session_id {session_id} not found in database")
            return False
        
        payment.status = status
        payment.verified_at = datetime.datetime.now() if status == PaymentStatus.SUCCESS else None
        payment.ref_id = result_data.get("payment_intent")
        payment.card_number = "****"  # Stripe doesn't provide card number in session
        payment.response_data = json.dumps(result_data)
        db.commit()
        
        # If payment was successful, set user as premium
        if status == PaymentStatus.SUCCESS:
            # payment.user_id is now the database user ID, so we can query directly
            user = db.query(User).filter(User.id == payment.user_id).first()
            if not user:
                # This should not happen since payment.user_id is now the database user ID
                # But if it does, we need to log it as an error
                logger.error(f"Critical: User with db_id {payment.user_id} not found when updating payment {session_id}")
                return False
            else:
                # Update existing user
                user.subscription_tier = SubscriptionTier.PREMIUM
                if user.subscription_expiry and user.subscription_expiry > datetime.datetime.now():
                    # Extend existing subscription
                    user.subscription_expiry = user.subscription_expiry + datetime.timedelta(days=30)
                else:
                    # New subscription period
                    user.subscription_expiry = datetime.datetime.now() + datetime.timedelta(days=30)
            
            db.commit()
            logger.info(f"User {payment.user_id} is now premium until {user.subscription_expiry}")
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Database error when updating payment status: {e}")
        return False
    finally:
        db.close()

def is_user_premium(user_id: int) -> bool:
    """
    Check if a user has premium status
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Boolean indicating if user has active premium status
    """
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return False
        
        return user.subscription_tier == SubscriptionTier.PREMIUM and user.subscription_expiry > datetime.datetime.now()
    except Exception as e:
        logger.error(f"Error checking premium status for user {user_id}: {e}")
        return False
    finally:
        db.close()

def handle_stripe_webhook(payload: str, sig_header: str) -> Dict[str, Any]:
    """
    Handle Stripe webhook events
    
    Args:
        payload: Raw webhook payload
        sig_header: Stripe signature header
        
    Returns:
        Dictionary with webhook processing results
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        return {
            "success": False,
            "message": "Stripe webhook secret not configured",
            "data": None
        }
    
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        
        logger.info(f"Received Stripe webhook event: {event['type']}")
        
        # Handle the event
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            session_id = session['id']
            
            # Verify and process the payment
            result = verify_payment(session_id)
            return result
        else:
            logger.info(f"Unhandled event type: {event['type']}")
            return {
                "success": True,
                "message": f"Event {event['type']} received but not processed",
                "data": event
            }
            
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return {
            "success": False,
            "message": "Invalid payload",
            "data": None
        }
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        return {
            "success": False,
            "message": "Invalid signature",
            "data": None
        }
    except Exception as e:
        logger.error(f"Exception during webhook processing: {e}")
        return {
            "success": False,
            "message": f"Error processing webhook: {str(e)}",
            "data": None
        }

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Test payment flow
    print("\n------ Testing Stripe Payment Integration ------\n")
    
    # Check if required environment variables are set
    if not settings.STRIPE_SECRET_KEY:
        print("ERROR: STRIPE_SECRET_KEY is not set in environment variables")
        sys.exit(1)
    
    if not settings.PAYMENT_CALLBACK_URL_BASE:
        print("WARNING: PAYMENT_CALLBACK_URL_BASE is not set. Using default callback URL for testing.")
    
    # Simple test case
    test_user_id = 12345
    test_chat_id = 12345
    test_amount = 999  # $9.99 in cents
    
    # Create a payment link
    print(f"Creating payment link for user_id: {test_user_id}, amount: {test_amount} cents")
    success, message, payment_url = create_payment_link(test_user_id, test_chat_id, test_amount)
    
    if success:
        print(f"SUCCESS: Payment link created: {payment_url}")
        print("\nTo complete the test:")
        print("1. Visit the link above in a browser")
        print("2. Complete or cancel the payment")
        print("3. The webhook should be called automatically")
        print("4. Check your database to verify the payment status was updated")
    else:
        print(f"ERROR: Failed to create payment link. Message: {message}")
    
    print("\n------ End of Payment Test ------\n") 