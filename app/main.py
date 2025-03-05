from dotenv import load_dotenv
from fastapi.logger import logger
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from app.services.conversion_service import AudioConversionService
# from models.conversion_request import ConversionRequest
import os
import logging
import os
from supabase import create_client, Client
from pathlib import Path

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

app = FastAPI()

@app.post("/convert")
async def convert_audio(
    file: UploadFile = File(...),
    supabase_storage_path_to_folder: str = Form(...),
    file_name_no_extension: str | None = Form(default=None),
    # conversion: ConversionRequest = None
):
    logger.debug(f"Received conversion request for file: {file.filename}")
    logger.debug(f"Target folder: {supabase_storage_path_to_folder}")
    
    if not supabase_storage_path_to_folder:
        logger.error("No supabase_storage_path_to_folder provided")
        raise HTTPException(status_code=400, detail="No supabase_storage_path_to_folder provided")
    
    if not file.filename:
        logger.error("No file provided")
        raise HTTPException(status_code=400, detail="No file provided")

    try:
        logger.debug("Starting audio conversion")
        converted_path = await AudioConversionService.convert_audio(
            input_file=file,
            target_format='mp3',
        )
        logger.debug(f"Audio conversion completed. Output path: {converted_path}")
        
        # Upload file to supabase
        logger.debug("Starting Supabase upload")
        with open(converted_path, 'rb') as f:
            bucket = "realease-experience-content"
            fileNameStem = Path(file.filename).stem
            path = f"{supabase_storage_path_to_folder}/{file_name_no_extension if file_name_no_extension else fileNameStem}.mp3"
            logger.debug(f"Uploading to path: {path}")
            response = supabase.storage.from_(bucket).upload(
                file=f,
                path=path,
                file_options={"cache-control": "3600", "upsert": "true"},
            )
            public_url = supabase.storage.from_(bucket).get_public_url(path)
            logger.debug(f"Upload completed. Public URL: {public_url}")

        # Create an async function for cleanup
        async def cleanup():
            try:
                if os.path.exists(converted_path):
                    logger.debug(f"Cleaning up temporary file: {converted_path}")
                    os.remove(converted_path)
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                
        await cleanup()
        return public_url

    except Exception as e:
        logger.error(f"Error during conversion process: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))