#!/usr/bin/env python3
"""
Test Stripe Integration - Development Mode

This script demonstrates how Stripe test mode works without needing a real account.
You can use the provided test API keys to create payments that won't charge real money.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_stripe_configuration():
    """Test if Stripe is configured correctly"""
    print("=== Stripe Test Mode Configuration ===\n")
    
    # Check if stripe is available
    try:
        import stripe
        print("✅ Stripe library installed")
        print(f"   Version: {getattr(stripe, '__version__', 'Unknown')}")
    except ImportError:
        print("❌ Stripe library not found. Install with: pip install stripe")
        return False
    
    # Check environment variables
    stripe_secret = os.getenv('STRIPE_SECRET_KEY', '')
    stripe_public = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET', '')
    callback_url = os.getenv('PAYMENT_CALLBACK_URL_BASE', '')
    
    print("\n=== Environment Configuration ===")
    print(f"STRIPE_SECRET_KEY: {'✅ Set' if stripe_secret else '❌ Missing'}")
    if stripe_secret:
        if stripe_secret.startswith('sk_test_'):
            print("  👍 Using test mode (safe for development)")
        elif stripe_secret.startswith('sk_live_'):
            print("  ⚠️  WARNING: Using live mode (real money!)")
        else:
            print("  ❓ Unknown key format")
    
    print(f"STRIPE_PUBLISHABLE_KEY: {'✅ Set' if stripe_public else '❌ Missing'}")
    print(f"STRIPE_WEBHOOK_SECRET: {'✅ Set' if webhook_secret else '❌ Missing'}")
    print(f"PAYMENT_CALLBACK_URL_BASE: {'✅ Set' if callback_url else '❌ Missing'}")
    
    return bool(stripe_secret and stripe_public)

def test_stripe_api():
    """Test Stripe API connectivity with test keys"""
    print("\n=== Testing Stripe API ===")
    
    try:
        import stripe
        
        # Set test API key
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
        
        if not stripe.api_key:
            print("❌ No API key found")
            return False
            
        print(f"Using API key: {stripe.api_key[:12]}...")
        
        # Test API connectivity by creating a test customer
        print("\n📝 Creating test customer...")
        customer = stripe.Customer.create(
            email="test@example.com",
            name="Test Customer",
            description="Test customer for bot development"
        )
        
        print(f"✅ Test customer created: {customer.id}")
        print(f"   Email: {customer.email}")
        print(f"   Name: {customer.name}")
        
        # Clean up - delete the test customer
        customer.delete()
        print("🗑️  Test customer deleted")
        
        return True
        
    except Exception as e:
        print(f"❌ Stripe API error: {e}")
        return False

def test_payment_flow():
    """Test creating a payment session (like the bot does)"""
    print("\n=== Testing Payment Flow ===")
    
    try:
        import stripe
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
        
        # Create a checkout session (like in the bot)
        print("💳 Creating test checkout session...")
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Premium Subscription',
                        'description': 'Test premium subscription for Telegram bot',
                    },
                    'unit_amount': 999,  # $9.99 in cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='http://localhost:5000/success',
            cancel_url='http://localhost:5000/cancel',
            metadata={
                'user_id': '12345',
                'chat_id': '12345',
                'test': 'true'
            }
        )
        
        print("✅ Checkout session created successfully!")
        print(f"   Session ID: {session.id}")
        print(f"   Payment URL: {session.url}")
        print(f"   Amount: ${session.amount_total/100:.2f}")
        
        print("\n🔍 What this means:")
        print("- The payment link would work in test mode")
        print("- Users can use test card numbers (like 4242 4242 4242 4242)")
        print("- No real money will be charged")
        print("- Perfect for development and testing!")
        
        return True
        
    except Exception as e:
        print(f"❌ Payment flow error: {e}")
        return False

def show_test_cards():
    """Show available test credit cards"""
    print("\n=== Test Credit Cards (For Testing) ===")
    print("Use these cards in test mode - they won't charge real money:")
    print("")
    print("✅ Successful payments:")
    print("   4242 4242 4242 4242  (Visa)")
    print("   5555 5555 5555 4444  (Mastercard)")
    print("   3782 822463 10005     (American Express)")
    print("")
    print("❌ Failed payments (for testing errors):")
    print("   4000 0000 0000 0002  (Card declined)")
    print("   4000 0000 0000 9995  (Insufficient funds)")
    print("")
    print("📝 For any test card:")
    print("   - Use any future expiration date (e.g., 12/25)")
    print("   - Use any 3-digit CVC (e.g., 123)")
    print("   - Use any ZIP code (e.g., 12345)")

def main():
    """Main test function"""
    print("🧪 Stripe Test Mode Integration Test")
    print("=" * 50)
    
    # Test 1: Configuration
    if not test_stripe_configuration():
        print("\n❌ Configuration test failed!")
        print("Please check your .env file and install required packages.")
        return
    
    # Test 2: API connectivity  
    if not test_stripe_api():
        print("\n❌ API test failed!")
        print("Please check your Stripe API keys.")
        return
    
    # Test 3: Payment flow
    if not test_payment_flow():
        print("\n❌ Payment flow test failed!")
        return
    
    # Show test cards
    show_test_cards()
    
    print("\n" + "=" * 50)
    print("🎉 All tests passed! Stripe integration is ready.")
    print("\n✨ How to test in the bot:")
    print("1. Click 'Unlimited Reminders 👑' button")
    print("2. Click 'Pay Now' to get Stripe checkout page")
    print("3. Use test cards above to complete payment")
    print("4. No real money will be charged!")

if __name__ == "__main__":
    main() 