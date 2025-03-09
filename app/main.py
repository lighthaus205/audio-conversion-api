from dotenv import load_dotenv
from fastapi.logger import logger
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from app.services.conversion_service import AudioConversionService
from app.services.environment_hdri_conversion import EnvironmentHdriConversionService
# from models.conversion_request import ConversionRequest
import os
import logging
from supabase import create_client, Client
from pathlib import Path
from app.logging_config import setup_logging
import asyncio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import shutil

load_dotenv()

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

# Create FastAPI app with unlimited file size
app = FastAPI()

# Add middleware to handle large files
class LargeFileMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/convert_environment_hdri", "/convert"]:
            # Remove any content length limits for these endpoints
            request._body_size_limit = None
        return await call_next(request)

app.add_middleware(LargeFileMiddleware)

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
    loop = asyncio.get_event_loop()

    try:
        # Fetch file from supabase
        logger.debug("Downloading file from Supabase")
        file_content = await loop.run_in_executor(
            None,
            lambda: supabase.storage.from_("realease-experience-content").download(convert_supabase_storage_path)
        )
        
        if not file_content:
            logger.error(f"File not found in supabase: {convert_supabase_storage_path}")
            raise HTTPException(status_code=400, detail=f"File not found in supabase: {convert_supabase_storage_path}")

        # Create a temporary file for the downloaded content
        temp_input_path = f"/tmp/{Path(convert_supabase_storage_path).name}"
        logger.debug(f"Saving downloaded file to: {temp_input_path}")
        
        # Write file in binary mode asynchronously
        async with asyncio.Lock():  # Ensure thread-safe file operations
            with open(temp_input_path, "wb") as f:
                f.write(file_content)
                f.flush()
                os.fsync(f.fileno())
        
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
        converted_path, loudness_data = await AudioConversionService.convert_audio(
            input_file=file,
            target_format='mp3',
            audio_quality=audio_quality,
        )
        logger.debug(f"Audio conversion completed. Output path: {converted_path}")
        
        # Upload file to supabase
        logger.debug("Starting Supabase upload")
        async with asyncio.Lock():  # Ensure thread-safe file operations
            with open(converted_path, 'rb') as f:
                bucket = "realease-experience-content"
                # Ensure the result path has .mp3 extension
                path = result_supabase_storage_path
                if not path.lower().endswith('.mp3'):
                    path = str(Path(path).with_suffix('.mp3'))
                logger.debug(f"Uploading to path: {path}")
                
                response = await loop.run_in_executor(
                    None,
                    lambda: supabase.storage.from_(bucket).upload(
                        path=path,
                        file=f,
                        file_options={
                            "cacheControl": "3600",
                            "upsert": "true",
                            "contentType": "audio/mpeg"
                        }
                    )
                )
                
                public_url = await loop.run_in_executor(
                    None,
                    lambda: supabase.storage.from_(bucket).get_public_url(path)
                )
                logger.debug(f"Upload completed. Public URL: {public_url}")

        # Extract key loudness metrics - keep as numeric values
        audio_metrics = {
            "integrated_loudness": loudness_data.get("integrated_loudness", "N/A"),
            "true_peak": loudness_data.get("true_peak", "N/A"),
            "loudness_range": loudness_data.get("loudness_range", "N/A"),
            "threshold": loudness_data.get("threshold", "N/A")
        }
        
        # Add units to the metrics for better readability in a separate object
        audio_metrics_formatted = {
            "integrated_loudness": f"{audio_metrics['integrated_loudness']} LUFS" if audio_metrics['integrated_loudness'] != "N/A" else "N/A",
            "true_peak": f"{audio_metrics['true_peak']} dBFS" if audio_metrics['true_peak'] != "N/A" else "N/A",
            "loudness_range": f"{audio_metrics['loudness_range']} LU" if audio_metrics['loudness_range'] != "N/A" else "N/A",
            "threshold": f"{audio_metrics['threshold']} LUFS" if audio_metrics['threshold'] != "N/A" else "N/A"
        }
        
        logger.debug(f"Audio metrics: {audio_metrics}")
        logger.debug(f"Formatted metrics: {audio_metrics_formatted}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Audio file converted and uploaded successfully",
                "data": {
                    "public_url": public_url,
                    "path": path,
                    "bucket": bucket,
                    "content_type": "audio/mpeg",
                    "audio_metrics": audio_metrics,  # Numeric values
                    "audio_metrics_formatted": audio_metrics_formatted  # Values with units
                }
            }
        )

    except Exception as e:
        logger.error(f"Error during conversion process: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e),
                "error": {
                    "type": type(e).__name__,
                    "detail": str(e)
                }
            }
        )
    finally:
        # Cleanup using async operations
        try:
            if temp_input_path and os.path.exists(temp_input_path):
                logger.debug(f"Cleaning up temporary input file: {temp_input_path}")
                await loop.run_in_executor(None, os.remove, temp_input_path)
            if converted_path and os.path.exists(converted_path):
                logger.debug(f"Cleaning up converted file: {converted_path}")
                await loop.run_in_executor(None, os.remove, converted_path)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")



@app.post("/convert_environment_hdri")
async def convert_environment_hdri(
    file: UploadFile = File(...),
    result_supabase_storage_path: str = Form(...),
):
    """
    Convert an environment HDRI file (EXR format) and upload to Supabase.
    
    Args:
        file: The EXR file to convert
        result_supabase_storage_path: The path in Supabase storage where the result will be stored
        
    Returns:
        JSON response with the public URL of the converted file
    """
    logger.debug(f"Received environment HDRI conversion request for file: {file.filename}")
    
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in EnvironmentHdriConversionService.SUPPORTED_FORMATS:
        logger.error(f"Unsupported file format: {file_ext}")
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Unsupported file format: {file_ext}. Supported formats are: {', '.join(EnvironmentHdriConversionService.SUPPORTED_FORMATS)}"
            }
        )
    
    temp_files = None
    loop = asyncio.get_event_loop()

    try:
        # Convert the HDRI file
        logger.debug("Starting environment HDRI conversion")
        converted_files, metadata = await EnvironmentHdriConversionService.convert(
            input_file=file,
        )
        
        if not converted_files:
            logger.error("HDRI conversion failed: No output files generated")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "HDRI conversion failed: No output files generated"
                }
            )
            
        logger.debug(f"HDRI conversion completed. Output files: {converted_files}")
        temp_files = metadata.get('temp_files', {})
        
        # Upload files to Supabase
        uploaded_files = []
        
        for converted_path in converted_files:
            file_name = os.path.basename(converted_path)
            file_path = f"{result_supabase_storage_path}"
            
            logger.debug(f"Uploading to path: {file_path}")
            
            async with asyncio.Lock():  # Ensure thread-safe file operations
                with open(converted_path, 'rb') as f:
                    bucket = "realease-experience-content"
                    
                    response = await loop.run_in_executor(
                        None,
                        lambda: supabase.storage.from_(bucket).upload(
                            path=file_path,
                            file=f,
                            file_options={
                                "cacheControl": "3600",
                                "upsert": "true",
                                "contentType": "image/x-exr"
                            }
                        )
                    )
                    
                    public_url = await loop.run_in_executor(
                        None,
                        lambda: supabase.storage.from_(bucket).get_public_url(file_path)
                    )
                    
                    uploaded_files.append({
                        "filename": file_name,
                        "path": file_path,
                        "public_url": public_url
                    })
                    
                    logger.debug(f"Upload completed. Public URL: {public_url}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Environment HDRI files converted and uploaded successfully",
                "data": {
                    "uploaded_files": uploaded_files,
                    "metadata": metadata
                }
            }
        )

    except Exception as e:
        logger.error(f"Error during HDRI conversion process: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e),
                "error": {
                    "type": type(e).__name__,
                    "detail": str(e)
                }
            }
        )
    finally:
        # Clean up temporary files after successful upload
        if temp_files:
            try:
                input_file = temp_files.get('input_file')
                output_dir = temp_files.get('output_dir')
                
                if input_file and os.path.exists(input_file):
                    logger.debug(f"Cleaning up input file: {input_file}")
                    await loop.run_in_executor(None, os.remove, input_file)
                    
                if output_dir and os.path.exists(output_dir):
                    logger.debug(f"Cleaning up output directory: {output_dir}")
                    await loop.run_in_executor(None, lambda: shutil.rmtree(output_dir))
                    
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")