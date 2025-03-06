import os
import uuid
import shutil
import subprocess
import logging
from fastapi import UploadFile
from pathlib import Path

logger = logging.getLogger(__name__)

class AudioConversionService:
    # List of common audio formats that FFmpeg can handle
    SUPPORTED_FORMATS = {
        '.mp3', '.wav', '.aac', '.m4a', '.wma', '.ogg', '.flac', 
        '.alac', '.aiff', '.webm', '.opus', '.mp2'
    }

    @staticmethod
    async def convert_audio(
        input_file: UploadFile, 
        target_format: str = 'mp3', 
        samplerate: str = '44100',
        audio_quality: str = '8'
    ):
        logger.debug(f"Starting audio conversion for file: {input_file.filename}")
        
        # Verify input file format
        file_ext = Path(input_file.filename).suffix.lower()
        if file_ext not in AudioConversionService.SUPPORTED_FORMATS:
            logger.error(f"Unsupported file format: {file_ext}")
            raise ValueError(f"Unsupported file format: {file_ext}. Supported formats are: {', '.join(AudioConversionService.SUPPORTED_FORMATS)}")
        
        # Create unique filename with UUID to avoid conflicts
        unique_id = str(uuid.uuid4())
        input_filename = f"/tmp/{unique_id}-{input_file.filename}"
        # Always use .mp3 extension for output file
        output_filename = f"/tmp/{unique_id}-converted.mp3"
        logger.debug(f"Input file path: {input_filename}")
        logger.debug(f"Output file path: {output_filename}")

        try:
            # Save uploaded file
            logger.debug("Saving uploaded file")
            with open(input_filename, "wb") as buffer:
                # Read in chunks to handle large files
                while content := await input_file.read(8192):
                    buffer.write(content)
            buffer.close()  # Ensure file is closed
            logger.debug("File saved successfully")

            # Verify file exists and has size
            if not os.path.exists(input_filename):
                raise ValueError("Input file was not saved properly")
            
            file_size = os.path.getsize(input_filename)
            logger.debug(f"Input file size: {file_size} bytes")
            
            if file_size == 0:
                raise ValueError("Input file is empty")

            # Perform conversion using FFmpeg with optimized settings
            logger.debug("Starting FFmpeg conversion")
            ffmpeg_command = [
                'ffmpeg',
                '-y',  # Overwrite output file
                '-i', input_filename,  # Input file
                '-map', '0:a:0',  # Select first audio stream
                '-codec:a', 'libmp3lame',  # Use LAME MP3 encoder
                '-q:a', audio_quality,  # Audio quality (VBR) - 0 best, 9 worst
                '-ar', samplerate,  # Audio sample rate
                '-ac', '2',  # Audio channels (stereo)
                '-map_metadata', '0',  # Copy metadata
                '-id3v2_version', '3',  # Use ID3v2.3 tags for better compatibility
                output_filename
            ]
            logger.debug(f"FFmpeg command: {' '.join(ffmpeg_command)}")
            
            # Run FFmpeg with progress monitoring
            result = subprocess.run(
                ffmpeg_command,
                check=True,
                capture_output=True,
                text=True
            )
            
            # Check FFmpeg output for warnings or information
            if result.stderr:
                logger.debug(f"FFmpeg output: {result.stderr}")
            
            logger.debug("FFmpeg conversion completed successfully")
            
            # Verify output file exists and has size
            if not os.path.exists(output_filename):
                raise ValueError("Output file was not created")
            
            output_size = os.path.getsize(output_filename)
            logger.debug(f"Output file size: {output_size} bytes")
            
            if output_size == 0:
                raise ValueError("Output file is empty")

            # Verify the output file is a valid MP3
            verify_command = [
                'ffmpeg',
                '-v', 'error',
                '-i', output_filename,
                '-f', 'null',
                '-'
            ]
            verify_result = subprocess.run(
                verify_command,
                capture_output=True,
                text=True
            )
            
            if verify_result.stderr:
                logger.error(f"Output file verification failed: {verify_result.stderr}")
                raise ValueError("Generated MP3 file is invalid or corrupted")

            return output_filename
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg conversion failed: {e.stderr}")
            error_msg = e.stderr if e.stderr else str(e)
            raise ValueError(f"Conversion failed: {error_msg}")
        except Exception as e:
            logger.error(f"Unexpected error during conversion: {str(e)}")
            raise
        finally:
            # Clean up input file
            try:
                if os.path.exists(input_filename):
                    logger.debug(f"Cleaning up input file: {input_filename}")
                    os.remove(input_filename)
            except Exception as e:
                logger.error(f"Error cleaning up input file: {e}")