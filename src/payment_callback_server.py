from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, HTMLResponse
import logging
import datetime
import httpx
from config.config import settings
from src.database import get_db
from src.models import User, Payment, SubscriptionTier

app = FastAPI()
logger = logging.getLogger("payment_callback")

SUCCESS_MESSAGE = (
    "✅ پرداخت موفق بود\n"
    "تبریک! 🎉 اشتراک یادآور نامحدود برای شما فعال شد.\n"
    f"از حالا تا {settings.PREMIUM_SUBSCRIPTION_DURATION_MONTHS} ماه آینده می‌تونی بدون محدودیت یادآور ثبت کنی.\n"
    "اگه سوالی داشتی، من اینجام!"
)
FAIL_MESSAGE = (
    "❌ پرداخت ناموفق بود\n"
    "پرداخت انجام نشد یا لغو شد.\n"
    "اگه مشکلی پیش اومده یا پرداختت ناقص مونده، می‌تونی دوباره تلاش کنی.\n"
    "اگه بازم مشکلی بود، به پشتیبانی پیام بده تا کمکت کنه"
)

TELEGRAM_API_URL = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
TELEGRAM_BOT_LINK = getattr(settings, 'TELEGRAM_BOT_LINK', None)
if not TELEGRAM_BOT_LINK:
    logger.warning("TELEGRAM_BOT_LINK is not set in settings. Please add it to your .env or config file.")

SUCCESS_HTML = f"""
<!DOCTYPE html>
<html lang='fa' dir='rtl'>
<head>
    <meta charset='UTF-8'>
    <title>پرداخت موفق</title>
    <style>
        body {{ background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); color: #222; font-family: Vazirmatn, Tahoma, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
        .card {{ background: #fff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 2.5rem 2rem; max-width: 400px; text-align: center; }}
        .emoji {{ font-size: 3rem; margin-bottom: 1rem; }}
        .btn {{ margin-top: 2rem; background: #43e97b; color: #fff; border: none; border-radius: 8px; padding: 0.75rem 2rem; font-size: 1.1rem; cursor: pointer; text-decoration: none; transition: background 0.2s; }}
        .btn:hover {{ background: #38f9d7; color: #222; }}
    </style>
</head>
<body>
    <div class='card'>
        <div class='emoji'>✅</div>
        <h2>پرداخت موفق بود</h2>
        <p>تبریک! 🎉 اشتراک یادآور نامحدود برای شما فعال شد.<br>از حالا تا {settings.PREMIUM_SUBSCRIPTION_DURATION_MONTHS} ماه آینده می‌تونی بدون محدودیت یادآور ثبت کنی.</p>
        <p>اگه سوالی داشتی، من اینجام!</p>
        <a class='btn' href='{TELEGRAM_BOT_LINK}' target='_blank'>بازگشت به ربات تلگرام</a>
    </div>
</body>
</html>
"""

FAIL_HTML = f"""
<!DOCTYPE html>
<html lang='fa' dir='rtl'>
<head>
    <meta charset='UTF-8'>
    <title>پرداخت ناموفق</title>
    <style>
        body {{ background: linear-gradient(135deg, #ff5858 0%, #f09819 100%); color: #222; font-family: Vazirmatn, Tahoma, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
        .card {{ background: #fff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 2.5rem 2rem; max-width: 400px; text-align: center; }}
        .emoji {{ font-size: 3rem; margin-bottom: 1rem; }}
        .btn {{ margin-top: 2rem; background: #ff5858; color: #fff; border: none; border-radius: 8px; padding: 0.75rem 2rem; font-size: 1.1rem; cursor: pointer; text-decoration: none; transition: background 0.2s; }}
        .btn:hover {{ background: #f09819; color: #222; }}
    </style>
</head>
<body>
    <div class='card'>
        <div class='emoji'>❌</div>
        <h2>پرداخت ناموفق بود</h2>
        <p>پرداخت انجام نشد یا لغو شد.<br>اگه مشکلی پیش اومده یا پرداختت ناقص مونده، می‌تونی دوباره تلاش کنی.<br>اگه بازم مشکلی بود، به پشتیبانی پیام بده تا کمکت کنه</p>
        <a class='btn' href='{TELEGRAM_BOT_LINK}' target='_blank'>بازگشت به ربات تلگرام</a>
    </div>
</body>
</html>
"""

@app.post("/payment_callback")
@app.post("//payment_callback")  # Handle double slash from Zibal
async def payment_callback(request: Request):
    data = await request.json()
    logger.info(f"Received payment callback: {data}")
    track_id = data.get("trackId")
    status_code = data.get("result")
    ref_number = data.get("refNumber")
    card_number = data.get("cardNumber")
    order_id = data.get("orderId")
    metadata = data.get("metadata", {})
    telegram_user_id = metadata.get("telegram_user_id")
    chat_id = metadata.get("chat_id")

    db = next(get_db())
    try:
        payment = db.query(Payment).filter(Payment.track_id == str(track_id)).first()
        if not payment:
            logger.error(f"Payment with track_id {track_id} not found in DB.")
            return JSONResponse(status_code=404, content={"detail": "Payment not found"})
        user = db.query(User).filter(User.id == payment.user_id).first()
        if not user:
            logger.error(f"User with id {payment.user_id} not found for payment {track_id}.")
            return JSONResponse(status_code=404, content={"detail": "User not found"})
        # Update payment record
        payment.status = status_code
        payment.ref_id = ref_number
        payment.card_number = card_number
        payment.response_data = str(data)
        payment.verified_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
        # Success
        if status_code == 100:
            # Mark user as premium
            user.subscription_tier = SubscriptionTier.PREMIUM
            user.subscription_expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30*settings.PREMIUM_SUBSCRIPTION_DURATION_MONTHS)
            db.commit()
            logger.info(f"User {user.id} marked as premium until {user.subscription_expiry}.")
            # Send Telegram message
            if chat_id:
                await send_telegram_message(chat_id, SUCCESS_MESSAGE)
            return {"success": True, "message": "Payment successful, user upgraded."}
        else:
            logger.info(f"Payment failed or cancelled for user {user.id}, status: {status_code}")
            if chat_id:
                await send_telegram_message(chat_id, FAIL_MESSAGE)
            return {"success": False, "message": "Payment failed or cancelled."}
    except Exception as e:
        logger.error(f"Exception in payment_callback: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": str(e)})
    finally:
        db.close()

@app.get("/payment_callback")
@app.get("//payment_callback")  # Handle double slash from Zibal
async def payment_callback_get(request: Request):
    params = dict(request.query_params)
    track_id = params.get("trackId")
    status_code = int(params.get("status", 0))
    order_id = params.get("orderId")
    success_flag = params.get("success")
    # You may want to parse more params as needed

    db = next(get_db())
    try:
        payment = db.query(Payment).filter(Payment.track_id == str(track_id)).first()
        if not payment:
            logger.error(f"[GET] Payment with track_id {track_id} not found in DB.")
            return HTMLResponse("<h2>پرداخت یافت نشد.</h2>", status_code=404)
        user = db.query(User).filter(User.id == payment.user_id).first()
        if not user:
            logger.error(f"[GET] User with id {payment.user_id} not found for payment {track_id}.")
            return HTMLResponse("<h2>کاربر یافت نشد.</h2>", status_code=404)
        # Update payment record
        payment.status = status_code
        payment.response_data = str(params)
        payment.verified_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
        # Success
        if status_code == 100 or (success_flag and success_flag == "1"):
            user.subscription_tier = SubscriptionTier.PREMIUM
            user.subscription_expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30*settings.PREMIUM_SUBSCRIPTION_DURATION_MONTHS)
            db.commit()
            logger.info(f"[GET] User {user.id} marked as premium until {user.subscription_expiry}.")
            return HTMLResponse(SUCCESS_HTML)
        else:
            logger.info(f"[GET] Payment failed or cancelled for user {user.id}, status: {status_code}")
            return HTMLResponse(FAIL_HTML)
    except Exception as e:
        logger.error(f"[GET] Exception in payment_callback: {e}", exc_info=True)
        return HTMLResponse(f"<h2>خطا: {e}</h2>", status_code=500)
    finally:
        db.close()

async def send_telegram_message(chat_id, text):
    if not chat_id:
        logger.warning("No chat_id provided to send_telegram_message. Cannot send Telegram message.")
        return
    async with httpx.AsyncClient() as client:
        payload = {"chat_id": chat_id, "text": text}
        try:
            resp = await client.post(TELEGRAM_API_URL, json=payload)
            logger.info(f"Sent Telegram message to {chat_id}: {resp.text}")
            if resp.status_code != 200:
                logger.error(f"Telegram API returned non-200 status: {resp.status_code}, body: {resp.text}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {chat_id}: {e}") 