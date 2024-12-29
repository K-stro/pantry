import os
import secrets
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import logging
from pathlib import Path
import json

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PasswordResetManager:
    def __init__(self):
        self.reset_tokens_file = Path("data/reset_tokens.json")
        self.verification_codes_file = Path("data/verification_codes.json")
        self.tokens = self._load_tokens()
        self.verification_codes = self._load_verification_codes()
        self.max_attempts = 3
        self.code_expiry = timedelta(minutes=15)
        logger.info("PasswordResetManager initialized")

    def _load_tokens(self):
        """Load existing reset tokens"""
        try:
            if self.reset_tokens_file.exists():
                with open(self.reset_tokens_file, 'r') as f:
                    return json.load(f)
            logger.info("No existing tokens file found, creating new")
            return {}
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            return {}

    def _load_verification_codes(self):
        """Load existing verification codes"""
        try:
            if self.verification_codes_file.exists():
                with open(self.verification_codes_file, 'r') as f:
                    return json.load(f)
            logger.info("No existing verification codes file found, creating new")
            return {}
        except Exception as e:
            logger.error(f"Error loading verification codes: {e}")
            return {}

    def _save_tokens(self):
        """Save reset tokens to file"""
        try:
            self.reset_tokens_file.parent.mkdir(exist_ok=True)
            with open(self.reset_tokens_file, 'w') as f:
                json.dump(self.tokens, f)
            logger.info("Tokens saved successfully")
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")

    def _save_verification_codes(self):
        """Save verification codes to file"""
        try:
            self.verification_codes_file.parent.mkdir(exist_ok=True)
            with open(self.verification_codes_file, 'w') as f:
                json.dump(self.verification_codes, f)
            logger.info("Verification codes saved successfully")
        except Exception as e:
            logger.error(f"Error saving verification codes: {e}")

    def generate_verification_code(self, email: str) -> str:
        """Generate a 6-digit verification code"""
        try:
            code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            expiry = (datetime.now() + self.code_expiry).isoformat()

            self.verification_codes[email] = {
                'code': code,
                'expiry': expiry,
                'attempts': 0
            }
            self._save_verification_codes()
            logger.info(f"Verification code generated for {email}")
            return code
        except Exception as e:
            logger.error(f"Error generating verification code: {e}")
            return None

    def verify_code(self, email: str, code: str) -> bool:
        """Verify the provided code"""
        try:
            if email not in self.verification_codes:
                logger.warning(f"No verification code found for {email}")
                return False

            code_data = self.verification_codes[email]
            expiry = datetime.fromisoformat(code_data['expiry'])

            if datetime.now() > expiry:
                logger.warning(f"Verification code expired for {email}")
                del self.verification_codes[email]
                self._save_verification_codes()
                return False

            if code_data['attempts'] >= self.max_attempts:
                logger.warning(f"Max verification attempts exceeded for {email}")
                del self.verification_codes[email]
                self._save_verification_codes()
                return False

            if code_data['code'] != code:
                code_data['attempts'] += 1
                self._save_verification_codes()
                logger.warning(f"Invalid verification code attempt for {email}")
                return False

            logger.info(f"Verification code validated successfully for {email}")
            return True
        except Exception as e:
            logger.error(f"Error verifying code: {e}")
            return False

    def generate_reset_token(self, email: str) -> str:
        """Generate a secure reset token"""
        try:
            token = secrets.token_urlsafe(32)
            expiry = (datetime.now() + timedelta(hours=1)).isoformat()

            self.tokens[token] = {
                'email': email,
                'expiry': expiry,
                'used': False
            }
            self._save_tokens()
            logger.info(f"Reset token generated for {email}")
            return token
        except Exception as e:
            logger.error(f"Error generating reset token: {e}")
            return None

    def verify_token(self, token: str) -> tuple[bool, str]:
        """Verify if a token is valid and not expired"""
        try:
            if token not in self.tokens:
                logger.warning("Invalid reset token")
                return False, "Invalid reset token"

            token_data = self.tokens[token]
            if token_data['used']:
                logger.warning("Token already used")
                return False, "Token has already been used"

            expiry = datetime.fromisoformat(token_data['expiry'])
            if datetime.now() > expiry:
                logger.warning("Token expired")
                return False, "Token has expired"

            logger.info(f"Token verified successfully for {token_data['email']}")
            return True, token_data['email']
        except Exception as e:
            logger.error(f"Error verifying token: {e}")
            return False, str(e)

    def mark_token_used(self, token: str):
        """Mark a token as used"""
        try:
            if token in self.tokens:
                self.tokens[token]['used'] = True
                self._save_tokens()
                logger.info(f"Token marked as used: {token}")
        except Exception as e:
            logger.error(f"Error marking token as used: {e}")

    def send_verification_email(self, email: str, code: str) -> bool:
        """Send verification code email"""
        try:
            msg = MIMEText(f"""
            Hello,

            Your verification code for password reset is: {code}

            This code will expire in 15 minutes.

            If you did not request this code, please ignore this email.

            Best regards,
            Community Pantry Team
            """)

            msg['Subject'] = 'Password Reset Verification Code'
            msg['From'] = os.environ['SMTP_USERNAME']
            msg['To'] = email

            with smtplib.SMTP(os.environ['SMTP_SERVER'], int(os.environ['SMTP_PORT'])) as server:
                server.starttls()
                server.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
                server.sendmail(msg['From'], [msg['To']], msg.as_string())

            logger.info(f"Verification email sent to {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send verification email: {e}")
            return False

    def send_reset_email(self, email: str, reset_url: str) -> bool:
        """Send password reset email"""
        try:
            msg = MIMEText(f"""
            Hello,

            You have requested to reset your password. Click the link below to proceed:

            {reset_url}

            This link will expire in 1 hour.

            If you did not request this reset, please ignore this email.

            Best regards,
            Community Pantry Team
            """)

            msg['Subject'] = 'Password Reset Request'
            msg['From'] = os.environ['SMTP_USERNAME']
            msg['To'] = email

            with smtplib.SMTP(os.environ['SMTP_SERVER'], int(os.environ['SMTP_PORT'])) as server:
                server.starttls()
                server.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
                server.sendmail(msg['From'], [msg['To']], msg.as_string())

            logger.info(f"Reset email sent to {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send reset email: {e}")
            return False

    def cleanup_expired_tokens(self):
        """Remove expired tokens"""
        try:
            current_time = datetime.now()
            self.tokens = {
                token: data for token, data in self.tokens.items()
                if datetime.fromisoformat(data['expiry']) > current_time
            }
            self._save_tokens()

            self.verification_codes = {
                email: data for email, data in self.verification_codes.items()
                if datetime.fromisoformat(data['expiry']) > current_time
            }
            self._save_verification_codes()
            logger.info("Cleanup of expired tokens completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")