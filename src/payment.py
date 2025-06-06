import logging
import json
import datetime
import requests
import sys
from typing import Dict, Any, Optional, Tuple, Union

from src.database import get_db
from src.models import User, Payment
from config.config import settings

logger = logging.getLogger(__name__)

# Zibal API endpoints
ZIBAL_REQUEST_URL = "https://gateway.zibal.ir/v1/request"
ZIBAL_VERIFY_URL = "https://gateway.zibal.ir/v1/verify"
ZIBAL_PAYMENT_GATEWAY = "https://gateway.zibal.ir/start/{track_id}"

# Default payment amount (100,000 Tomans in Rials)
DEFAULT_PAYMENT_AMOUNT = 1000000

class ZibalPaymentError(Exception):
    """Exception raised for errors in Zibal payment processing."""
    pass

class PaymentStatus:
    """Status codes returned by Zibal API"""
    SUCCESS = 100
    FAILED = 102
    CANCELED = 201
    PENDING = 1  # Custom status for internal tracking

def create_payment_link(user_id: int, chat_id: int, amount: int = DEFAULT_PAYMENT_AMOUNT) -> Tuple[bool, str, Optional[str]]:
    """
    Create a payment link using Zibal API
    
    Args:
        user_id: Telegram user ID
        chat_id: Telegram chat ID
        amount: Payment amount in Rials
        
    Returns:
        (success, message, payment_url) tuple where:
        - success: Boolean indicating if operation was successful
        - message: Description message
        - payment_url: URL to redirect user to (if success is True)
    """
    callback_url = f"{settings.PAYMENT_CALLBACK_URL_BASE}/payment_callback" if settings.PAYMENT_CALLBACK_URL_BASE else "https://example.com/payment_callback"
    
    data = {
        "merchant": settings.ZIBAL_MERCHANT_KEY,
        "amount": amount,
        "callbackUrl": callback_url,
        "description": f"Premium subscription for Telegram bot user {user_id}",
        "orderId": f"telegram-user-{user_id}-{int(datetime.datetime.now().timestamp())}",
        "metadata": {
            "user_id": user_id,
            "chat_id": chat_id
        }
    }
    
    try:
        response = requests.post(ZIBAL_REQUEST_URL, json=data)
        result = response.json()
        
        if response.status_code == 200 and result.get("result") == 100:
            track_id = result.get("trackId")
            payment_url = ZIBAL_PAYMENT_GATEWAY.format(track_id=track_id)
            
            # Save payment info to database
            db = next(get_db())
            try:
                # Create payment record
                payment = Payment(
                    user_id=user_id,
                    chat_id=chat_id,
                    track_id=str(track_id),
                    amount=amount,
                    status=PaymentStatus.PENDING,
                    created_at=datetime.datetime.now()
                )
                db.add(payment)
                db.commit()
                
                logger.info(f"Created payment link for user {user_id} with track_id {track_id}")
                return True, "Payment link created successfully", payment_url
                
            except Exception as e:
                db.rollback()
                logger.error(f"Database error when creating payment: {e}")
                return False, "Internal server error when recording payment", None
            finally:
                db.close()
        else:
            error_code = result.get("result")
            error_message = result.get("message", "Unknown error")
            logger.error(f"Zibal payment creation failed: {error_code} - {error_message}")
            return False, f"Payment gateway error: {error_message}", None
            
    except Exception as e:
        logger.error(f"Exception during payment link creation: {e}")
        return False, "Failed to connect to payment gateway", None

def verify_payment(track_id: str) -> Dict[str, Any]:
    """
    Verify a payment with Zibal
    
    Args:
        track_id: The track ID received from Zibal
        
    Returns:
        Dictionary with verification results including success status
    """
    data = {
        "merchant": settings.ZIBAL_MERCHANT_KEY,
        "trackId": track_id
    }
    
    try:
        response = requests.post(ZIBAL_VERIFY_URL, json=data)
        result = response.json()
        
        # Log verification details
        logger.info(f"Payment verification result for track_id {track_id}: {json.dumps(result)}")
        
        # Process verification result
        status = result.get("result")
        
        if status == PaymentStatus.SUCCESS:
            # Update payment status in database
            update_payment_status(track_id, status, result)
            return {
                "success": True,
                "message": "Payment verified successfully",
                "data": result
            }
        else:
            update_payment_status(track_id, status, result)
            return {
                "success": False,
                "message": f"Payment verification failed: {result.get('message', 'Unknown error')}",
                "data": result
            }
            
    except Exception as e:
        logger.error(f"Exception during payment verification: {e}")
        return {
            "success": False,
            "message": f"Error verifying payment: {str(e)}",
            "data": None
        }

def update_payment_status(track_id: str, status: int, result_data: Dict[str, Any]) -> bool:
    """
    Update payment status in database
    
    Args:
        track_id: The track ID of the payment
        status: Status code from Zibal
        result_data: Full response data from Zibal
        
    Returns:
        Boolean indicating if update was successful
    """
    db = next(get_db())
    try:
        payment = db.query(Payment).filter(Payment.track_id == track_id).first()
        
        if not payment:
            logger.error(f"Payment with track_id {track_id} not found in database")
            return False
        
        payment.status = status
        payment.verified_at = datetime.datetime.now() if status == PaymentStatus.SUCCESS else None
        payment.ref_id = result_data.get("refNumber")
        payment.card_number = result_data.get("cardNumber")
        payment.response_data = json.dumps(result_data)
        db.commit()
        
        # If payment was successful, set user as premium
        if status == PaymentStatus.SUCCESS:
            user = db.query(User).filter(User.user_id == payment.user_id).first()
            if not user:
                # Create user if not exists
                user = User(
                    user_id=payment.user_id,
                    chat_id=payment.chat_id,
                    is_premium=True,
                    premium_until=datetime.datetime.now() + datetime.timedelta(days=30)  # 30 days subscription
                )
                db.add(user)
            else:
                # Update existing user
                user.is_premium = True
                if user.premium_until and user.premium_until > datetime.datetime.now():
                    # Extend existing subscription
                    user.premium_until = user.premium_until + datetime.timedelta(days=30)
                else:
                    # New subscription period
                    user.premium_until = datetime.datetime.now() + datetime.timedelta(days=30)
            
            db.commit()
            logger.info(f"User {payment.user_id} is now premium until {user.premium_until}")
        
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
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
        
        return user.is_premium and user.premium_until > datetime.datetime.now()
    except Exception as e:
        logger.error(f"Error checking premium status for user {user_id}: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Test payment flow
    print("\n------ Testing Zibal Payment Integration ------\n")
    
    # Check if required environment variables are set
    if not settings.ZIBAL_MERCHANT_KEY:
        print("ERROR: ZIBAL_MERCHANT_KEY is not set in environment variables")
        sys.exit(1)
    
    if not settings.PAYMENT_CALLBACK_URL_BASE:
        print("WARNING: PAYMENT_CALLBACK_URL_BASE is not set. Using default callback URL for testing.")
    
    # Simple test case
    test_user_id = 12345
    test_chat_id = 12345
    test_amount = 10000  # 10,000 Rials
    
    # Create a payment link
    print(f"Creating payment link for user_id: {test_user_id}, amount: {test_amount} Rials")
    success, message, payment_url = create_payment_link(test_user_id, test_chat_id, test_amount)
    
    if success:
        print(f"SUCCESS: Payment link created: {payment_url}")
        print("\nTo complete the test:")
        print("1. Visit the link above in a browser")
        print("2. Complete or cancel the payment")
        print("3. The callback URL should be called automatically")
        print("4. Check your database to verify the payment status was updated")
    else:
        print(f"ERROR: Failed to create payment link. Message: {message}")
    
    print("\n------ End of Payment Test ------\n") 