import os
import uuid
import shutil
import subprocess
import logging
from fastapi import UploadFile

logger = logging.getLogger(__name__)

class AudioConversionService:
    @staticmethod
    async def convert_audio(
        input_file: UploadFile, 
        target_format: str = 'mp3', 
        samplerate: str = '44100'
    ):
        logger.debug(f"Starting audio conversion for file: {input_file.filename}")
        
        # Create unique filename
        input_filename = f"/tmp/{input_file.filename}"
        output_filename = f"/tmp/{input_file.filename}-converted.{target_format}"
        logger.debug(f"Input file path: {input_filename}")
        logger.debug(f"Output file path: {output_filename}")

        # Save uploaded file
        logger.debug("Saving uploaded file")
        with open(input_filename, "wb") as buffer:
            shutil.copyfileobj(input_file.file, buffer)
        logger.debug("File saved successfully")

        # Perform conversion using FFmpeg
        try:
            logger.debug("Starting FFmpeg conversion")
            ffmpeg_command = [
                'ffmpeg', 
                '-y',
                '-i', input_filename, 
                '-q:a', '7', # Audio quality i.e. bitrate
                '-ar', samplerate, # Audio sample rate
                '-ac', '2', # Audio channels
                output_filename
            ]
            logger.debug(f"FFmpeg command: {' '.join(ffmpeg_command)}")
            
            result = subprocess.run(
                ffmpeg_command,
                check=True,
                capture_output=True,
                text=True
            )
            logger.debug("FFmpeg conversion completed successfully")
            return output_filename
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg conversion failed: {e.stderr}")
            raise ValueError(f"Conversion failed: {str(e)}")
        finally:
            # Clean up input file
            try:
                if os.path.exists(input_filename):
                    logger.debug(f"Cleaning up input file: {input_filename}")
                    os.remove(input_filename)
            except Exception as e:
                logger.error(f"Error cleaning up input file: {e}")