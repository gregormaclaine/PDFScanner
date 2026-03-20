import sys
import bcrypt

def hash_password(password: str):
    """Utility to generate a secure BCrypt hash for your .env file."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python util_hash.py <your_password>")
        sys.exit(1)
    
    password = sys.argv[1]
    hashed = hash_password(password)
    print("\nSECRET HASH FOR .env:")
    print("----------------------------")
    print(f"ADMIN_PASSWORD_HASH={hashed}")
    print("----------------------------\n")
