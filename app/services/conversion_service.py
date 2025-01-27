import os
import uuid
import shutil
import subprocess
from fastapi import UploadFile

class AudioConversionService:
    @staticmethod
    async def convert_audio(
        input_file: UploadFile, 
        target_format: str = 'mp3', 
        samplerate: str = '44100'
    ):
        # Create unique filename
        input_filename = f"/tmp/{input_file.filename}"
        output_filename = f"/tmp/{input_file.filename}-converted.{target_format}"

        # Save uploaded file
        with open(input_filename, "wb") as buffer:
            shutil.copyfileobj(input_file.file, buffer)

        # Perform conversion using FFmpeg
        try:
            subprocess.run([
                'ffmpeg', 
                '-y',
                '-i', input_filename, 
                '-q:a', '7', # Audio quality i.e. bitrate
                '-ar', samplerate, # Audio sample rate
                '-ac', '2', # Audio channels
                output_filename
            ], check=True)

            return output_filename
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Conversion failed: {str(e)}")
        finally:
            # Clean up input file
            os.remove(input_filename)