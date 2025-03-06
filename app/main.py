from dotenv import load_dotenv
from fastapi.logger import logger
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from app.services.conversion_service import AudioConversionService
# from models.conversion_request import ConversionRequest
import os
import logging
from supabase import create_client, Client
from pathlib import Path
from app.logging_config import setup_logging

load_dotenv()

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

app = FastAPI()

@app.post("/convert")
async def convert_audio(
    convert_supabase_storage_path: str = Form(...),
    result_supabase_storage_path: str = Form(...),
    audio_quality: str = Form(default='8'),
):
    logger.debug(f"Received conversion request for path: {convert_supabase_storage_path}")
    logger.debug(f"Target path: {result_supabase_storage_path}")
    
    if not convert_supabase_storage_path:
        logger.error("No convert_supabase_storage_path provided")
        raise HTTPException(status_code=400, detail="No convert_supabase_storage_path provided")

    temp_input_path = None
    converted_path = None

    try:
        # Fetch file from supabase
        logger.debug("Downloading file from Supabase")
        file_content = supabase.storage.from_("realease-experience-content").download(convert_supabase_storage_path)
        
        if not file_content:
            logger.error(f"File not found in supabase: {convert_supabase_storage_path}")
            raise HTTPException(status_code=400, detail=f"File not found in supabase: {convert_supabase_storage_path}")

        # Create a temporary file for the downloaded content
        temp_input_path = f"/tmp/{Path(convert_supabase_storage_path).name}"
        logger.debug(f"Saving downloaded file to: {temp_input_path}")
        
        # Write file in binary mode
        with open(temp_input_path, "wb") as f:
            f.write(file_content)
            f.flush()
            os.fsync(f.fileno())  # Ensure file is written to disk
        
        # Verify file was written
        if not os.path.exists(temp_input_path):
            raise HTTPException(status_code=500, detail="Failed to save temporary file")
        
        file_size = os.path.getsize(temp_input_path)
        logger.debug(f"Downloaded file size: {file_size} bytes")
        
        if file_size == 0:
            raise HTTPException(status_code=400, detail="Downloaded file is empty")

        # Create an UploadFile object for the conversion service
        file = UploadFile(
            file=open(temp_input_path, "rb"),
            filename=Path(convert_supabase_storage_path).name
        )

        logger.debug("Starting audio conversion")
        converted_path = await AudioConversionService.convert_audio(
            input_file=file,
            target_format='mp3',
            audio_quality=audio_quality,
        )
        logger.debug(f"Audio conversion completed. Output path: {converted_path}")
        
        # Upload file to supabase
        logger.debug("Starting Supabase upload")
        with open(converted_path, 'rb') as f:
            bucket = "realease-experience-content"
            # Ensure the result path has .mp3 extension
            path = result_supabase_storage_path
            if not path.lower().endswith('.mp3'):
                # If path doesn't end with .mp3, remove any existing extension and add .mp3
                path = str(Path(path).with_suffix('.mp3'))
            logger.debug(f"Uploading to path: {path}")
            response = supabase.storage.from_(bucket).upload(
                file=f,
                path=path,
                file_options={
                    "cacheControl": "3600",
                    "upsert": "true",
                    "contentType": "audio/mpeg"
                }
            )
            public_url = supabase.storage.from_(bucket).get_public_url(path)
            logger.debug(f"Upload completed. Public URL: {public_url}")

        return public_url

    except Exception as e:
        logger.error(f"Error during conversion process: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup
        try:
            if temp_input_path and os.path.exists(temp_input_path):
                logger.debug(f"Cleaning up temporary input file: {temp_input_path}")
                os.remove(temp_input_path)
            if converted_path and os.path.exists(converted_path):
                logger.debug(f"Cleaning up converted file: {converted_path}")
                os.remove(converted_path)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")