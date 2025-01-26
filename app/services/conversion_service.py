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
        bitrate: str = '192k'
    ):
        # Create unique filename
        input_filename = f"/tmp/{input_file.filename}"
        output_filename = f"/tmp/{input_file.filename}-converted.{target_format}"
        
        
        print('input_filename')
        print(input_filename)
        print('output_filename 1')
        print(output_filename)

        # Save uploaded file
        with open(input_filename, "wb") as buffer:
            shutil.copyfileobj(input_file.file, buffer)

        # Perform conversion using FFmpeg
        try:
            subprocess.run([
                'ffmpeg', 
                '-i', input_filename, 
                '-b:a', bitrate, 
                '-vn',  # Ignore video
                output_filename
            ], check=True)
            
            print('output_filename 2')
            print(output_filename)

            return output_filename
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Conversion failed: {str(e)}")
        finally:
            # Clean up input file
            os.remove(input_filename)