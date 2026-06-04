import asyncio
import os
import sys

# Ensure backend package can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from backend.core.database import AsyncSessionLocal
from backend.models.user import User
from backend.services.tool_settings_service import get_user_tool_settings

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).limit(1))
        user = res.scalar_one_or_none()
        if not user:
            print("No user found!")
            return
        print(f"User found: {user.username} (ID: {user.id})")
        try:
            settings = await get_user_tool_settings(db, user)
            print("Success:", settings)
        except Exception as e:
            print("ERROR:")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
