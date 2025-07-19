from flask import Flask, render_template_string
import os

app = Flask(__name__)

# Privacy Policy HTML template
PRIVACY_POLICY_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy - AI Reminder Bot</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background-color: #f9f9f9;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 30px;
        }
        h3 {
            color: #7f8c8d;
        }
        .highlight {
            background-color: #ecf0f1;
            padding: 15px;
            border-left: 4px solid #3498db;
            margin: 20px 0;
        }
        .contact-info {
            background-color: #e8f5e8;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .last-updated {
            font-style: italic;
            color: #7f8c8d;
            text-align: center;
            margin-top: 30px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Privacy Policy for AI Reminder Bot</h1>
        <p class="last-updated">Last Updated: July 19, 2025</p>

        <h2>1. Introduction</h2>
        <p>Welcome to AI Reminder Bot (the "Bot"), a service provided by [Your Full Name] ("I," "me," or "my"). This Privacy Policy explains how I collect, use, store, and share your information when you use my Telegram bot. Your privacy is critically important to me. This policy is designed to be compliant with data protection regulations such as the GDPR, which applies to users in Europe.</p>
        
        <p>By using the Bot, you agree to the collection and use of information in accordance with this policy.</p>

        <h2>2. Information I Collect</h2>
        
        <h3>Telegram User Information</h3>
        <p>When you start using the Bot, I receive your public Telegram User ID and first name. This is necessary to identify you as a user and deliver reminders.</p>

        <h3>Reminder Content</h3>
        <p>I collect the content of the reminders you set via text or voice message. This data is essential for the Bot's core function.</p>

        <h3>Timezone Information</h3>
        <p>To send reminders accurately, I collect your timezone. You can provide this by sending a location pin or by sending the name of your city or country. If you send a location pin, it is used only once to determine your timezone and is not stored.</p>

        <h3>Payment Information</h3>
        <p>For premium users, payment processing is handled by our third-party provider, Stripe. I do not collect or store your full credit card details. I only receive a confirmation of your subscription status and a Stripe Customer ID from Stripe to manage your premium account.</p>

        <h2>3. How I Use Your Information</h2>
        <p>Your data is used exclusively for the following purposes:</p>
        <ul>
            <li>To provide, operate, and maintain the Bot's services.</li>
            <li>To set reminders and send you notifications at the correct time based on your timezone.</li>
            <li>To process your premium subscription and manage your account status.</li>
            <li>To respond to your support requests sent via email or Telegram.</li>
            <li>To improve the Bot's functionality and user experience.</li>
        </ul>

        <h2>4. Third-Party Data Processors</h2>
        <p>I use trusted third-party services to operate the Bot. These services have their own privacy policies and are responsible for the data they process.</p>

        <div class="highlight">
            <h3>Supabase</h3>
            <p>All user data, including your Telegram User ID, reminder content, timezone, and subscription status, is securely stored using Supabase.</p>

            <h3>Google Cloud Services</h3>
            <p>When you set a reminder using a voice message, the audio file is sent to Google's speech-to-text service for transcription. The audio file is deleted from my systems as soon as the transcription process is complete.</p>

            <h3>Stripe</h3>
            <p>All premium subscription payments are processed securely by Stripe. Your payment details are sent directly to Stripe and are not handled by me.</p>

            <h3>Telegram</h3>
            <p>The Bot operates on the Telegram platform. Your interactions with Telegram are governed by Telegram's own Privacy Policy.</p>
        </div>

        <h2>5. Data Retention and Deletion</h2>
        <p>I believe in data minimization and only store your data for as long as it is necessary.</p>

        <h3>Reminder Data</h3>
        <p>When you delete a reminder or it is marked as complete, it is "soft-deleted" (marked as inactive). After one (1) month of being soft-deleted, this data is permanently and automatically erased from our database.</p>

        <h3>Account Deletion</h3>
        <p>You have the right to request the complete deletion of all your data. To do so, please contact me at ai_reminder@gmail.com.</p>

        <h2>6. Your Data Protection Rights (GDPR)</h2>
        <p>If you are a resident of the European Economic Area (EEA), you have certain data protection rights, including:</p>
        <ul>
            <li><strong>The right to access:</strong> You can request copies of your personal data.</li>
            <li><strong>The right to rectification:</strong> You can request that I correct any information you believe is inaccurate or complete information you believe is incomplete.</li>
            <li><strong>The right to erasure:</strong> You can request that I erase your personal data, under certain conditions.</li>
            <li><strong>The right to restrict processing:</strong> You have the right to request that I restrict the processing of your personal data.</li>
            <li><strong>The right to object to processing:</strong> You have the right to object to my processing of your personal data.</li>
            <li><strong>The right to data portability:</strong> You have the right to request that I transfer the data that I have collected to another organization, or directly to you.</li>
        </ul>
        <p>To exercise any of these rights, please contact me at ai_reminder@gmail.com.</p>

        <h2>7. Changes to This Privacy Policy</h2>
        <p>I may update this Privacy Policy from time to time. I will notify you of any changes by posting the new policy and updating the "Last Updated" date.</p>

        <h2>8. Contact Me</h2>
        <div class="contact-info">
            <p>For any questions about this Privacy Policy or to exercise your rights, please contact me at <strong>ai_reminder@gmail.com</strong>.</p>
        </div>
    </div>
</body>
</html>
"""

# Terms of Service HTML template
TERMS_OF_SERVICE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terms of Service - AI Reminder Bot</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background-color: #f9f9f9;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 30px;
        }
        .highlight {
            background-color: #ecf0f1;
            padding: 15px;
            border-left: 4px solid #3498db;
            margin: 20px 0;
        }
        .last-updated {
            font-style: italic;
            color: #7f8c8d;
            text-align: center;
            margin-top: 30px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Terms of Service for AI Reminder Bot</h1>
        <p class="last-updated">Last Updated: July 19, 2025</p>

        <h2>1. Acceptance of Terms</h2>
        <p>By using the AI Reminder Bot ("the Bot"), you agree to be bound by these Terms of Service. If you do not agree to these terms, please do not use the Bot.</p>

        <h2>2. Description of Service</h2>
        <p>The Bot is a Telegram-based reminder service that allows users to create, manage, and receive notifications for personal reminders. The service includes:</p>
        <ul>
            <li>Creating reminders via text or voice messages</li>
            <li>Automatic timezone detection and conversion</li>
            <li>Reminder notifications with snooze functionality</li>
            <li>Premium features for unlimited reminders</li>
        </ul>

        <h2>3. User Responsibilities</h2>
        <p>You agree to:</p>
        <ul>
            <li>Use the Bot only for lawful purposes</li>
            <li>Not attempt to reverse engineer or hack the Bot</li>
            <li>Not use the Bot to send spam or inappropriate content</li>
            <li>Maintain the security of your Telegram account</li>
        </ul>

        <h2>4. Premium Subscription</h2>
        <div class="highlight">
            <p><strong>Free Tier:</strong> Limited to 5 active reminders</p>
            <p><strong>Premium Tier:</strong> Unlimited reminders for $9.99/month</p>
            <p>Premium subscriptions are processed through Stripe and are billed monthly. You may cancel your subscription at any time.</p>
        </div>

        <h2>5. Service Availability</h2>
        <p>While I strive to maintain high availability, the Bot may experience downtime due to maintenance, updates, or technical issues. I am not liable for any damages resulting from service interruptions.</p>

        <h2>6. Data and Privacy</h2>
        <p>Your privacy is important. Please review our Privacy Policy for details on how we handle your data. By using the Bot, you consent to our data practices as described in the Privacy Policy.</p>

        <h2>7. Limitation of Liability</h2>
        <p>The Bot is provided "as is" without warranties of any kind. I shall not be liable for any indirect, incidental, special, or consequential damages arising from your use of the Bot.</p>

        <h2>8. Changes to Terms</h2>
        <p>I reserve the right to modify these terms at any time. Changes will be effective immediately upon posting. Your continued use of the Bot constitutes acceptance of the modified terms.</p>

        <h2>9. Contact Information</h2>
        <p>For questions about these Terms of Service, please contact me at ai_reminder@gmail.com.</p>
    </div>
</body>
</html>
"""

# Contact page HTML template
CONTACT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Contact Us - AI Reminder Bot</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background-color: #f9f9f9;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        .contact-method {
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #3498db;
        }
        .contact-method h3 {
            color: #2c3e50;
            margin-top: 0;
        }
        .email-link {
            color: #3498db;
            text-decoration: none;
            font-weight: bold;
        }
        .email-link:hover {
            text-decoration: underline;
        }
        .response-time {
            font-style: italic;
            color: #7f8c8d;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Contact Us</h1>
        <p>We're here to help! If you have any questions, concerns, or need support with the AI Reminder Bot, please don't hesitate to reach out.</p>

        <div class="contact-method">
            <h3>📧 Email Support</h3>
            <p>For general inquiries, technical support, or privacy concerns:</p>
            <p><a href="mailto:ai_reminder@gmail.com" class="email-link">ai_reminder@gmail.com</a></p>
            <p class="response-time">We typically respond within 24 hours.</p>
        </div>

        <div class="contact-method">
            <h3>🔒 Privacy & Data Requests</h3>
            <p>For privacy-related questions, data deletion requests, or GDPR rights:</p>
            <p><a href="mailto:ai_reminder@gmail.com" class="email-link">ai_reminder@gmail.com</a></p>
            <p class="response-time">Privacy requests are processed within 48 hours.</p>
        </div>

        <div class="contact-method">
            <h3>💳 Payment & Subscription Support</h3>
            <p>For billing questions, subscription management, or payment issues:</p>
            <p><a href="mailto:ai_reminder@gmail.com" class="email-link">ai_reminder@gmail.com</a></p>
            <p class="response-time">Payment support available within 12 hours.</p>
        </div>

        <div class="contact-method">
            <h3>🐛 Bug Reports & Feature Requests</h3>
            <p>Found a bug or have a feature suggestion? Let us know:</p>
            <p><a href="mailto:ai_reminder@gmail.com" class="email-link">ai_reminder@gmail.com</a></p>
            <p class="response-time">We review all feedback and respond to confirmed bugs within 24 hours.</p>
        </div>

        <h2>What to Include in Your Message</h2>
        <p>To help us assist you better, please include:</p>
        <ul>
            <li>Your Telegram username (if applicable)</li>
            <li>A clear description of your issue or question</li>
            <li>Steps to reproduce the problem (for bug reports)</li>
            <li>Screenshots if relevant</li>
        </ul>

        <h2>Response Times</h2>
        <p>We strive to respond to all inquiries promptly:</p>
        <ul>
            <li><strong>Urgent issues:</strong> Within 12 hours</li>
            <li><strong>General support:</strong> Within 24 hours</li>
            <li><strong>Privacy requests:</strong> Within 48 hours</li>
            <li><strong>Feature requests:</strong> Within 72 hours</li>
        </ul>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return "AI Reminder Bot - Legal Pages Server"

@app.route('/privacy')
def privacy():
    return PRIVACY_POLICY_HTML

@app.route('/terms')
def terms():
    return TERMS_OF_SERVICE_HTML

@app.route('/contact')
def contact():
    return CONTACT_HTML

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False) 