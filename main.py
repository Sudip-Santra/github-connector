import uvicorn
from dotenv import load_dotenv
import os

load_dotenv()

if __name__ == "__main__":
    host = os.getenv("HOST")
    port = int(os.getenv("PORT"))
    uvicorn.run("app:app", host=host, port=port, reload=True)
