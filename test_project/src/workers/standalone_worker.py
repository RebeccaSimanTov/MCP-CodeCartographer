"""
Re-export standalone worker from services.workers
This allows running: python -m src.workers.standalone_worker
"""
from src.services.workers.standalone_worker import *

if __name__ == "__main__":
    import sys
    from src.services.workers.standalone_worker import main
    import asyncio
    asyncio.run(main())
