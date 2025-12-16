# Environment File Encryption

This project uses encrypted environment variables to protect sensitive credentials.

## Setup Instructions

### First Time Setup

1. **Install cryptography library:**
   ```bash
   pip install cryptography
   ```

2. **Encrypt your .env file:**
   ```bash
   python encrypt_env.py encrypt
   ```
   - You'll be prompted to enter an encryption password
   - Remember this password! You'll need it to decrypt the file
   - This creates `.env.encrypted` from your `.env` file

3. **Commit the encrypted file:**
   ```bash
   git add .env.encrypted
   git commit -m "Add encrypted environment variables"
   ```

4. **Never commit the plaintext .env file** (it's in .gitignore)

### For Other Developers / Deployments

1. **Clone the repository**

2. **Decrypt the environment file:**
   ```bash
   python encrypt_env.py decrypt
   ```
   - Enter the encryption password (get it from team lead/secure channel)
   - This creates `.env` from `.env.encrypted`

3. **Run the application:**
   ```bash
   python webapp/app.py
   ```

## Security Notes

- ✅ `.env.encrypted` - Safe to commit to version control
- ❌ `.env` - Never commit (contains plaintext secrets)
- 🔐 Encryption password - Share securely (not in git/email)

## Commands

- `python encrypt_env.py encrypt` - Encrypt .env → .env.encrypted
- `python encrypt_env.py decrypt` - Decrypt .env.encrypted → .env

## Encryption Method

- Uses Fernet (symmetric encryption) from the `cryptography` library
- Password is hashed with SHA-256 to derive encryption key
- AES-128 encryption in CBC mode with HMAC authentication
