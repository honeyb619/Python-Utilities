#!/usr/bin/env python3
"""
Encrypt/Decrypt .env file to protect sensitive credentials
Usage:
    python encrypt_env.py encrypt  - Encrypts .env to .env.encrypted
    python encrypt_env.py decrypt  - Decrypts .env.encrypted to .env
"""

import sys
import os
from pathlib import Path
from cryptography.fernet import Fernet
import getpass

def get_encryption_key():
    """Get or create encryption key from user password"""
    # Prompt for password
    password = getpass.getpass("Enter encryption password: ")
    
    # Derive a key from the password (simple approach - use 32 bytes)
    # For production, use proper KDF like PBKDF2
    from hashlib import sha256
    key = sha256(password.encode()).digest()
    
    # Fernet requires base64-encoded 32-byte key
    import base64
    return base64.urlsafe_b64encode(key)

def encrypt_env():
    """Encrypt .env file"""
    env_file = Path(__file__).parent / ".env"
    encrypted_file = Path(__file__).parent / ".env.encrypted"
    
    if not env_file.exists():
        print("❌ .env file not found!")
        return False
    
    # Read .env content
    with open(env_file, 'rb') as f:
        data = f.read()
    
    # Get encryption key from password
    key = get_encryption_key()
    
    # Encrypt
    fernet = Fernet(key)
    encrypted_data = fernet.encrypt(data)
    
    # Write encrypted file
    with open(encrypted_file, 'wb') as f:
        f.write(encrypted_data)
    
    print(f"✅ Encrypted .env → .env.encrypted")
    print(f"⚠️  Keep .env.encrypted in version control")
    print(f"⚠️  Add .env to .gitignore")
    print(f"⚠️  Remember your encryption password!")
    return True

def decrypt_env():
    """Decrypt .env.encrypted file"""
    encrypted_file = Path(__file__).parent / ".env.encrypted"
    env_file = Path(__file__).parent / ".env"
    
    if not encrypted_file.exists():
        print("❌ .env.encrypted file not found!")
        return False
    
    # Read encrypted content
    with open(encrypted_file, 'rb') as f:
        encrypted_data = f.read()
    
    # Get encryption key from password
    key = get_encryption_key()
    
    try:
        # Decrypt
        fernet = Fernet(key)
        decrypted_data = fernet.decrypt(encrypted_data)
        
        # Write .env file
        with open(env_file, 'wb') as f:
            f.write(decrypted_data)
        
        print(f"✅ Decrypted .env.encrypted → .env")
        return True
    except Exception as e:
        print(f"❌ Decryption failed! Wrong password or corrupted file.")
        print(f"   Error: {str(e)}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python encrypt_env.py encrypt  - Encrypt .env file")
        print("  python encrypt_env.py decrypt  - Decrypt .env.encrypted file")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "encrypt":
        encrypt_env()
    elif command == "decrypt":
        decrypt_env()
    else:
        print(f"❌ Unknown command: {command}")
        print("Use 'encrypt' or 'decrypt'")
        sys.exit(1)

if __name__ == "__main__":
    main()
