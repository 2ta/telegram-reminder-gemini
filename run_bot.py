import asyncio
from src.bot import build_application

if __name__ == "__main__":
    app = build_application()
    asyncio.run(app.run_polling()) 