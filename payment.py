import logging
import json
import datetime
import requests
from typing import Dict, Any, Optional, Tuple, Union

from database import get_db, User, Payment
from config import ZIBAL_MERCHANT_KEY, TELEGRAM_BOT_URL, PAYMENT_AMOUNT

logger = logging.getLogger(__name__)

# Zibal API endpoints
ZIBAL_REQUEST_URL = "https://gateway.zibal.ir/v1/request"
ZIBAL_VERIFY_URL = "https://gateway.zibal.ir/v1/verify"
ZIBAL_PAYMENT_GATEWAY = "https://gateway.zibal.ir/start/{track_id}"

class PaymentStatus:
    """Status codes returned by Zibal API"""
    SUCCESS = 100
    FAILED = 102
    CANCELED = 201
    PENDING = 1  # Custom status for internal tracking

def create_payment_link(user_id: int, chat_id: int, amount: int = PAYMENT_AMOUNT) -> Tuple[bool, str, Optional[str]]:
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
    callback_url = f"{TELEGRAM_BOT_URL}/payment_callback"
    
    data = {
        "merchant": ZIBAL_MERCHANT_KEY,
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
        "merchant": ZIBAL_MERCHANT_KEY,
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