import os
import uuid
import shutil
import subprocess
import logging
import asyncio
import json
import re
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
        output_filename = f"/tmp/{unique_id}-converted.mp3"
        loudness_log = f"/tmp/{unique_id}-loudness.txt"
        logger.debug(f"Input file path: {input_filename}")
        logger.debug(f"Output file path: {output_filename}")

        try:
            # Save uploaded file asynchronously
            logger.debug("Saving uploaded file")
            async with asyncio.Lock():  # Ensure thread-safe file operations
                with open(input_filename, "wb") as buffer:
                    while content := await input_file.read(8192):
                        buffer.write(content)
            logger.debug("File saved successfully")

            # Verify file exists and has size
            if not os.path.exists(input_filename):
                raise ValueError("Input file was not saved properly")
            
            file_size = os.path.getsize(input_filename)
            logger.debug(f"Input file size: {file_size} bytes")
            
            if file_size == 0:
                raise ValueError("Input file is empty")

            # Run FFmpeg to analyze loudness using ebur128 filter
            loop = asyncio.get_event_loop()
            logger.debug("Analyzing audio loudness with ebur128 filter")
            
            # First, analyze the audio with ebur128 filter
            loudness_command = [
                'ffmpeg',
                '-i', input_filename,
                '-filter_complex', 'ebur128=peak=true:meter=18',
                '-f', 'null',
                '-'
            ]
            
            loudness_result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    loudness_command,
                    check=True,
                    capture_output=True,
                    text=True
                )
            )
            
            # Extract loudness information from stderr output
            loudness_data = {
                "integrated_loudness": "N/A",
                "true_peak": "N/A",
                "loudness_range": "N/A",
                "threshold": "N/A"
            }
            
            try:
                # Parse the ebur128 output
                output = loudness_result.stderr
                
                # Extract integrated loudness (I)
                integrated_match = re.search(r'I:\s*([-\d.]+)\s*LUFS', output)
                if integrated_match:
                    loudness_data["integrated_loudness"] = float(integrated_match.group(1))
                
                # Extract true peak
                true_peak_match = re.search(r'Peak:\s*([-\d.]+)\s*dBFS', output)
                if true_peak_match:
                    loudness_data["true_peak"] = float(true_peak_match.group(1))
                
                # Extract LRA (Loudness Range)
                lra_match = re.search(r'LRA:\s*([-\d.]+)\s*LU', output)
                if lra_match:
                    loudness_data["loudness_range"] = float(lra_match.group(1))
                
                # Extract threshold
                threshold_match = re.search(r'Threshold:\s*([-\d.]+)\s*LUFS', output)
                if threshold_match:
                    loudness_data["threshold"] = float(threshold_match.group(1))
                
                logger.debug(f"Loudness analysis results: {loudness_data}")
            except Exception as e:
                logger.error(f"Error parsing loudness data: {e}")
                logger.debug(f"Raw loudness output: {output}")

            # Run FFmpeg in a thread pool to avoid blocking
            ffmpeg_command = [
                'ffmpeg',
                '-y',
                '-i', input_filename,
                '-map', '0:a:0',
                '-codec:a', 'libmp3lame',
                '-q:a', audio_quality,
                '-ar', samplerate,
                '-ac', '2',
                '-compression_level', '0',
                '-map_metadata', '0',
                '-id3v2_version', '3',
                '-b:a', '96k',
                '-minrate', '96k',
                '-maxrate', '256k',
                '-bufsize', '512k',
                output_filename
            ]
            logger.debug(f"Starting FFmpeg conversion: {' '.join(ffmpeg_command)}")
            
            # Run FFmpeg in thread pool
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ffmpeg_command,
                    check=True,
                    capture_output=True,
                    text=True
                )
            )
            
            if result.stderr:
                logger.debug(f"FFmpeg output: {result.stderr}")
            
            logger.debug("FFmpeg conversion completed successfully")
            
            # Verify output file
            if not os.path.exists(output_filename):
                raise ValueError("Output file was not created")
            
            output_size = os.path.getsize(output_filename)
            logger.debug(f"Output file size: {output_size} bytes")
            
            if output_size == 0:
                raise ValueError("Output file is empty")

            # Verify MP3 in thread pool
            verify_command = [
                'ffmpeg',
                '-v', 'error',
                '-i', output_filename,
                '-f', 'null',
                '-'
            ]
            verify_result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    verify_command,
                    capture_output=True,
                    text=True
                )
            )
            
            if verify_result.stderr:
                logger.error(f"Output file verification failed: {verify_result.stderr}")
                raise ValueError("Generated MP3 file is invalid or corrupted")

            return output_filename, loudness_data
            
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
                    await loop.run_in_executor(None, os.remove, input_filename)
            except Exception as e:
                logger.error(f"Error cleaning up input file: {e}")