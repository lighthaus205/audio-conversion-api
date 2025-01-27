from dotenv import load_dotenv
from fastapi.logger import logger
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from services.conversion_service import AudioConversionService
# from models.conversion_request import ConversionRequest
import os
import logging
import os
from supabase import create_client, Client
from pathlib import Path

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)

app = FastAPI()

@app.post("/convert")
async def convert_audio(
    file: UploadFile = File(...),
    realease_experience_address: str = Form(...),
    # conversion: ConversionRequest = None
):
    if not realease_experience_address:
        raise HTTPException(status_code=400, detail="No realease_experience_address provided")
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    try:
        converted_path = await AudioConversionService.convert_audio(
            input_file=file,
            target_format='mp3',
        )
        
        # Upload file to supabase
        with open(converted_path, 'rb') as f:
            bucket = "realease-experience-content"
            fileNameStem = Path(file.filename).stem
            path = f"{realease_experience_address}/{fileNameStem}.mp3"
            response = supabase.storage.from_(bucket).upload(
                file=f,
                path=path,
                file_options={"cache-control": "3600", "upsert": "true"},
            )
            public_url = supabase.storage.from_(bucket).get_public_url(path)

        # Create an async function for cleanup
        async def cleanup():
            try:
                if os.path.exists(converted_path):
                    os.remove(converted_path)
            except Exception as e:
                print(f"Error during cleanup: {e}")
                
                
        await cleanup()
        return public_url

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))