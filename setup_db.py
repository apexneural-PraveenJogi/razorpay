"""
Database setup script for Razorpay FastAPI integration.
This script helps set up the PostgreSQL database.
"""
import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from database import Base, engine
from config import settings


async def setup_database():
    """Create all database tables."""
    try:
        print(f"Connecting to database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'N/A'}")
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        print("✅ Database tables created successfully!")
        return True
    except Exception as e:
        print(f"❌ Database setup failed: {str(e)}")
        print("\nTroubleshooting:")
        print("1. Make sure PostgreSQL is running: sudo systemctl start postgresql")
        print("2. Create database: createdb razorpay_db")
        print("3. Check DATABASE_URL in .env file")
        print("4. Verify PostgreSQL credentials")
        return False


async def test_connection():
    """Test database connection."""
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.scalar()
        print("✅ Database connection successful!")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        return False


async def main():
    """Main setup function."""
    print("=" * 50)
    print("Razorpay FastAPI - Database Setup")
    print("=" * 50)
    print()
    
    # Test connection first
    print("Testing database connection...")
    if not await test_connection():
        sys.exit(1)
    
    print()
    print("Setting up database tables...")
    if await setup_database():
        print()
        print("=" * 50)
        print("Database setup completed successfully!")
        print("=" * 50)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
