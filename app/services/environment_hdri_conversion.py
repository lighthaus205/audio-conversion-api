import os
import logging
from fastapi import UploadFile
from pathlib import Path
import OpenEXR
import Imath
import numpy as np
from skimage.transform import resize
import os
import uuid
import asyncio

logger = logging.getLogger(__name__)


def compress_exr(input_path, output_dir):
    """
    Compress an .exr file: reduce bit depth to 16-bit, downscale to 2K, and apply ZIP compression.
    
    Args:
        input_path (str): Path to the input .exr file.
        output_dir (str): Directory to save the compressed output files.
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Open the input .exr file
    exr_file = OpenEXR.InputFile(input_path)
    header = exr_file.header()

    # Get the data window (dimensions)
    dw = header['dataWindow']
    width = dw.max.x - dw.min.x + 1
    height = dw.max.y - dw.min.y + 1
    logger.debug(f"Input dimensions: {width}x{height}")

    # Define channel type (FLOAT for 32-bit, HALF for 16-bit)
    FLOAT = Imath.PixelType(Imath.PixelType.FLOAT)
    HALF = Imath.PixelType(Imath.PixelType.HALF)

    # Read RGB and Alpha channels as 32-bit float
    channels = ['R', 'G', 'B', 'A']
    pixel_data = {}
    for ch in channels:
        if ch in header['channels']:
            data = np.frombuffer(exr_file.channel(ch, FLOAT), dtype=np.float32)
            pixel_data[ch] = data.reshape(height, width)

    # Target 2K resolution (maintain aspect ratio)
    target_width = 2048
    target_height = 1024
    logger.debug(f"Processing 2K resolution: {target_width}x{target_height}")
    
    # Resize the image using skimage.transform.resize
    resized_data = {}
    for ch in pixel_data:
        # Convert to 2D array and resize
        img = pixel_data[ch]
        resized_img = resize(img, (target_height, target_width), mode='reflect', anti_aliasing=True, preserve_range=True)
        resized_data[ch] = resized_img  # Keep as 32-bit float during processing, no transpose
        logger.debug(f"Resized channel {ch} to shape: {resized_data[ch].shape}")

    # Update header for new resolution and compression
    new_header = header.copy()
    new_header['dataWindow'] = Imath.Box2i(Imath.V2i(0, 0), Imath.V2i(target_width - 1, target_height - 1))
    new_header['displayWindow'] = new_header['dataWindow']
    new_header['compression'] = OpenEXR.ZIP_COMPRESSION
    
    # Update channel formats to HALF (16-bit float)
    for ch in new_header['channels']:
        new_header['channels'][ch] = Imath.Channel(HALF)

    # Define output path
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}_2K_ZIP.exr")
    logger.debug(f"Saving with ZIP compression to: {output_path}")

    try:
        # Write the new .exr file
        output_file = OpenEXR.OutputFile(output_path, new_header)
        output_data = {}
        for ch in resized_data:
            # Convert to 16-bit float only at write time and ensure data is contiguous
            data_16bit = resized_data[ch].astype(np.float16)
            output_data[ch] = np.ascontiguousarray(data_16bit).tobytes()
        output_file.writePixels(output_data)
        output_file.close()
        logger.debug(f"Successfully saved: {output_path}")
    except Exception as e:
        logger.error(f"Error saving {output_path}: {str(e)}")
        raise

    logger.debug("Compression complete!")


class EnvironmentHdriConversionService:
    # List of supported formats
    SUPPORTED_FORMATS = {
        '.exr',
    }

    @staticmethod
    async def convert(
        input_file: UploadFile, 
    ):
        """
        Convert an environment HDRI file.
        
        Args:
            input_file: The uploaded file to convert
            
        Returns:
            Tuple containing a list of output file paths and metadata
        """
        logger.debug(f"Starting HDRI conversion for file: {input_file.filename}")
        
        # Create unique filename with UUID to avoid conflicts
        unique_id = str(uuid.uuid4())
        input_filename = f"/tmp/{unique_id}-{input_file.filename}"
        output_dir = f"/tmp/{unique_id}-output"
        
        try:
            # Save uploaded file in chunks
            logger.debug(f"Saving uploaded file to: {input_filename}")
            CHUNK_SIZE = 1024 * 1024  # 1MB chunks
            
            async with asyncio.Lock():  # Ensure thread-safe file operations
                with open(input_filename, "wb") as buffer:
                    while True:
                        chunk = await input_file.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        buffer.write(chunk)
                        
            logger.debug("File saved successfully")
            
            # Verify file exists and has size
            if not os.path.exists(input_filename):
                raise ValueError("Input file was not saved properly")
            
            file_size = os.path.getsize(input_filename)
            logger.debug(f"Input file size: {file_size} bytes")
            
            if file_size == 0:
                raise ValueError("Input file is empty")
            
            # Create output directory
            os.makedirs(output_dir, exist_ok=True)
            
            # Perform the actual compression
            logger.debug("Starting EXR compression")
            compress_exr(input_filename, output_dir)
            logger.debug("EXR compression completed")
            
            # Get list of generated files
            output_files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith('.exr')]
            
            if not output_files:
                raise ValueError("No output files were generated during compression")
            
            # Get compression results
            compression_results = []
            for output_file in output_files:
                output_size = os.path.getsize(output_file)
                compression_ratio = (file_size - output_size) / file_size * 100
                compression_results.append({
                    "file": os.path.basename(output_file),
                    "original_size": file_size,
                    "compressed_size": output_size,
                    "compression_ratio": f"{compression_ratio:.1f}%"
                })
            
            # Metadata about the conversion
            metadata = {
                "original_filename": input_file.filename,
                "original_size": file_size,
                "conversion_type": "EXR compression",
                "compression_results": compression_results,
                "temp_files": {  # Add temp file info for cleanup
                    "input_file": input_filename,
                    "output_dir": output_dir
                }
            }
            
            # Return the list of output files and metadata
            return output_files, metadata
            
        except Exception as e:
            logger.error(f"Error during HDRI conversion: {str(e)}")
            # Clean up only on error
            try:
                if os.path.exists(input_filename):
                    os.remove(input_filename)
                if os.path.exists(output_dir):
                    import shutil
                    shutil.rmtree(output_dir)
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup: {cleanup_error}")
            raise