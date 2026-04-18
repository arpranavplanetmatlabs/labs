
import asyncio
from qdrant_client import QdrantClient
from config import QDRANT_URL
import json

async def check_jobs():
    client = QdrantClient(url=QDRANT_URL)
    try:
        results, _ = client.scroll(
            collection_name="job_status",
            limit=100,
            with_vectors=False
        )
        for point in results:
            print(json.dumps(point.payload, indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import sys
    import os
    # Add current dir to path to import config
    sys.path.append(os.getcwd())
    asyncio.run(check_jobs())
