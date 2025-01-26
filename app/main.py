from fastapi.logger import logger
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from services.conversion_service import AudioConversionService
from models.conversion_request import ConversionRequest
import os
import logging

logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)

app = FastAPI()

@app.post("/convert")
async def convert_audio(
    file: UploadFile = File(...), 
    conversion: ConversionRequest = None
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        converted_path = await AudioConversionService.convert_audio(
            input_file=file,
            target_format=conversion.target_format if conversion else 'mp3',
            bitrate=conversion.bitrate if conversion else '192k'
        )
        
        print('converted_path')
        print(converted_path)
        
        # Upload file to supabase
        # TO DO

        # Create an async function for cleanup
        async def cleanup():
            try:
                if os.path.exists(converted_path):
                    os.remove(converted_path)
            except Exception as e:
                print(f"Error during cleanup: {e}")

        # Return converted file with background task
        response = converted_path
        
        # Use background parameter with an awaitable coroutine
        response.background = asyncio.create_task(cleanup())

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))