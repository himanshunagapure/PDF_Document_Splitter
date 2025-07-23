import os
import json
import base64
# from flask import Flask, request, jsonify  # Removed Flask imports
# from werkzeug.utils import secure_filename  # Moved to new API file
import PyPDF2
from PyPDF2 import PdfReader, PdfWriter
import google.generativeai as genai
from PIL import Image
import io
import fitz  # PyMuPDF for PDF to image conversion
import logging
from typing import List, Dict, Any
import tempfile
import shutil
from dotenv import load_dotenv
load_dotenv()
from pymongo import MongoClient
import datetime
from datetime import datetime, timezone
import sys
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Removed Flask app and route definitions ---
# app = Flask(__name__)

# Configuration
# UPLOAD_FOLDER = 'uploads'
# PROCESSED_FOLDER = 'processed'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

# MongoDB configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
MONGO_DB = os.getenv('MONGO_DB', 'document_splitter')
MONGO_COLLECTION = os.getenv('MONGO_COLLECTION', 'token_usage')

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB]
token_collection = mongo_db[MONGO_COLLECTION]

# Create directories if they don't exist
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# Configure Gemini API
# You need to set your API key as an environment variable or replace with your actual key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your-gemini-api-key-here')
genai.configure(api_key=GEMINI_API_KEY)

class DocumentProcessor:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
    def is_image_file(self, filename: str) -> bool:
        """Check if file is an image"""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
    
    def is_pdf_file(self, filename: str) -> bool:
        """Check if file is a PDF"""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'
    
    def get_pdf_page_count(self, pdf_path: str) -> int:
        """Get number of pages in PDF"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                return len(pdf_reader.pages)
        except Exception as e:
            logger.error(f"Error reading PDF {pdf_path}: {e}")
            return 0
    
    def pdf_to_images(self, pdf_path: str) -> List[str]:
        """Convert PDF pages to base64 encoded images"""
        try:
            doc = fitz.open(pdf_path)
            images = []
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Convert page to image
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
                img_data = pix.tobytes("png")
                
                # Convert to base64
                img_b64 = base64.b64encode(img_data).decode('utf-8')
                images.append(img_b64)
            
            doc.close()
            return images
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            return []
    
    def analyze_pdf_with_gemini(self, pdf_path: str) -> Dict[str, Any]:
        """Analyze PDF with Gemini and get document structure, including token usage if available"""
        try:
            page_count = self.get_pdf_page_count(pdf_path)
            if page_count == 0:
                return {"error": "PDF has no pages or could not be read."}

            # Convert PDF to images
            images = self.pdf_to_images(pdf_path)
            if not images:
                return {"error": "Failed to convert PDF to images"}
            # Prepare the prompt
            prompt = f"""
            Analyze this multi-page PDF document, which has {page_count} pages, and identify all the distinct documents within it.
            For each document type you identify, provide:
            1. document_type: The type of document (e.g., "Aadhar Card", "Passport", "Bank Statement", "Invoice", etc.).
            2. page_numbers: Array of page numbers that belong to this document (1-indexed).
            3. suggested_filename: A clean filename for this document (without extension).
            4. reason: Brief explanation of why you identified this as this document type.

            Return the response as a JSON object with this structure:
            {{
                "documents": [
                    {{
                        "document_type": "Document Type",
                        "page_numbers": [1, 2],
                        "suggested_filename": "document_name",
                        "reason": "Explanation of identification"
                    }}
                ],
                "total_pages": {page_count},
                "analysis_confidence": "high/medium/low"
            }}

            IMPORTANT: You must account for every single page. The 'page_numbers' in your response must collectively include all pages from 1 to {page_count}. Do not skip any pages. If you cannot classify a page, group it with other unclassified pages into a single document with the type "Unclassified Document".
            """
            # Prepare images for Gemini
            image_parts = []
            for i, img_b64 in enumerate(images):
                image_parts.append({
                    "mime_type": "image/png",
                    "data": img_b64
                })
            # Generate content with Gemini
            response = self.model.generate_content([prompt] + image_parts)
            # Parse response
            response_text = response.text
            # Try to extract JSON from response
            try:
                # Find JSON in response
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                json_str = response_text[start_idx:end_idx]
                analysis_result = json.loads(json_str)
                # Extract token usage if available
                input_tokens = None
                output_tokens = None
                total_tokens = None
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    input_tokens = getattr(response.usage_metadata, 'prompt_token_count', None)
                    output_tokens = getattr(response.usage_metadata, 'candidates_token_count', None)
                    total_tokens = getattr(response.usage_metadata, 'total_token_count', None)
                # Attach token info to analysis_result
                analysis_result['input_tokens'] = input_tokens
                analysis_result['output_tokens'] = output_tokens
                analysis_result['total_tokens'] = total_tokens
                return analysis_result
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON from Gemini response")
                return {"error": "Failed to parse analysis result", "raw_response": response_text}
        except Exception as e:
            logger.error(f"Error analyzing PDF with Gemini: {e}")
            return {"error": str(e)}
    
    def split_pdf_by_pages(self, pdf_path: str, page_ranges: List[tuple], output_dir: str, filename: str) -> str:
        """Split PDF based on page ranges"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                
                # Create PDF writer
                pdf_writer = PdfWriter()
                
                # Add pages based on range (convert from 1-indexed to 0-indexed)
                for page_num in range(page_ranges[0] - 1, page_ranges[1]):
                    if page_num < len(pdf_reader.pages):
                        pdf_writer.add_page(pdf_reader.pages[page_num])
                
                # Save split PDF
                output_path = os.path.join(output_dir, f"{filename}.pdf")
                with open(output_path, 'wb') as output_file:
                    pdf_writer.write(output_file)
                
                return output_path
                
        except Exception as e:
            logger.error(f"Error splitting PDF: {e}")
            return None
    
    def cut_pdf_by_page_numbers(self, pdf_path: str, start_page: int, end_page: int) -> str:
        """
        Cuts a PDF from start_page to end_page and saves it in the same folder.

        Args:
            pdf_path (str): The path to the input PDF file.
            start_page (int): The starting page number (1-indexed).
            end_page (int): The ending page number (1-indexed).

        Returns:
            str: The path to the newly created PDF file, or None if an error occurred.
        """
        try:
            if not os.path.exists(pdf_path):
                logger.error(f"PDF file not found at: {pdf_path}")
                return None

            output_dir = os.path.dirname(pdf_path)
            original_filename = os.path.splitext(os.path.basename(pdf_path))[0]
            # Create a filename for the new split PDF
            new_filename = f"{original_filename}_pages_{start_page}_to_{end_page}"
            
            with open(pdf_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                total_pages = len(pdf_reader.pages)

                # Validate page numbers
                if not (1 <= start_page <= end_page <= total_pages):
                    logger.error(f"Invalid page range for PDF with {total_pages} pages: start={start_page}, end={end_page}")
                    return None

                pdf_writer = PdfWriter()

                # Add pages to the writer object
                for page_num in range(start_page - 1, end_page):
                    pdf_writer.add_page(pdf_reader.pages[page_num])

                # Save the new PDF
                output_path = os.path.join(output_dir, f"{new_filename}.pdf")
                with open(output_path, 'wb') as output_file:
                    pdf_writer.write(output_file)

                logger.info(f"Successfully created cut PDF: {output_path}")
                return output_path

        except Exception as e:
            logger.error(f"Error cutting PDF: {e}")
            return None
    
    def process_folder(self, folder_path: str) -> Dict[str, Any]:
        """Process all files in the given folder"""
        results = {
            "processed_files": [],
            "skipped_files": [],
            "errors": [],
            "output_files": []
        }
        
        if not os.path.exists(folder_path):
            results["errors"].append(f"Folder path does not exist: {folder_path}")
            return results
        
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            
            if os.path.isfile(file_path):
                try:
                    # Check if it's an image file
                    if self.is_image_file(filename):
                        results["skipped_files"].append({
                            "filename": filename,
                            "reason": "Image file - skipped as requested",
                            "path": file_path
                        })
                        continue
                    
                    # Check if it's a PDF file
                    if self.is_pdf_file(filename):
                        page_count = self.get_pdf_page_count(file_path)
                        
                        if page_count == 0:
                            results["errors"].append({
                                "filename": filename,
                                "error": "Could not read PDF or empty PDF"
                            })
                            continue
                        
                        if page_count == 1:
                            results["skipped_files"].append({
                                "filename": filename,
                                "reason": "Single page PDF - skipped as requested",
                                "path": file_path,
                                "page_count": page_count
                            })
                            continue
                        
                        # Process multi-page PDF
                        logger.info(f"Processing multi-page PDF: {filename} ({page_count} pages)")
                        
                        # Analyze with Gemini
                        analysis_result = self.analyze_pdf_with_gemini(file_path)
                        
                        if "error" in analysis_result:
                            results["errors"].append({
                                "filename": filename,
                                "error": analysis_result["error"]
                            })
                            continue
                        
                        # Split PDF based on analysis
                        output_files = self.split_pdf_documents(file_path, analysis_result, folder_path)
                        
                        results["processed_files"].append({
                            "filename": filename,
                            "page_count": page_count,
                            "analysis": analysis_result,
                            "output_files": output_files
                        })
                        
                        results["output_files"].extend(output_files)
                        
                    else:
                        results["skipped_files"].append({
                            "filename": filename,
                            "reason": "Not a PDF or image file",
                            "path": file_path
                        })
                        
                except Exception as e:
                    results["errors"].append({
                        "filename": filename,
                        "error": str(e)
                    })
        
        return results
    
    def split_pdf_documents(self, pdf_path: str, analysis_result: Dict[str, Any], output_dir: str) -> list:
        """Split PDF into individual documents based on analysis, propagate token info, and ensure no pages are missed."""
        output_files = []
        try:
            documents = analysis_result.get("documents", [])
            total_pages_in_pdf = self.get_pdf_page_count(pdf_path)

            # Collect all page numbers from the analysis
            processed_pages = set()
            for doc in documents:
                for page_num in doc.get("page_numbers", []):
                    processed_pages.add(page_num)

            # Identify unclassified pages (from LLM output)
            all_pages = set(range(1, total_pages_in_pdf + 1))
            unclassified_pages = sorted(list(all_pages - processed_pages))

            # If there are unclassified pages, add them as a new document
            if unclassified_pages:
                documents.append({
                    "document_type": "Unclassified Document",
                    "page_numbers": unclassified_pages,
                    "suggested_filename": "unclassified_document",
                    "reason": "Pages not classified by the model."
                })
                logger.warning(f"Found {len(unclassified_pages)} unclassified pages: {unclassified_pages}")

            # Get the original combined filename (without extension)
            original_filename = os.path.splitext(os.path.basename(pdf_path))[0]
            # Get token info from analysis_result
            input_tokens = analysis_result.get('input_tokens')
            output_tokens = analysis_result.get('output_tokens')
            total_tokens = analysis_result.get('total_tokens')
            written_pages = set()
            for doc in documents:
                page_numbers = doc.get("page_numbers", [])
                document_type = doc.get("document_type", "Unknown")
                if not page_numbers:
                    continue
                # Slugify document_type: lowercase, replace spaces with hyphens
                doc_type_slug = doc.get("document_type", "unknown").lower().replace(' ', '-').replace('_', '-')
                # Page numbers as dash-joined string
                page_numbers_str = "-".join(str(p) for p in sorted(page_numbers))
                # Compose new filename
                new_filename = f"{original_filename}_{doc_type_slug}_{page_numbers_str}"
                # Split PDF
                output_path = self.split_pdf_by_pages(
                    pdf_path,
                    (min(page_numbers), max(page_numbers)),
                    output_dir,
                    new_filename
                )
                if output_path:
                    output_files.append({
                        "filename": os.path.basename(output_path),
                        "path": output_path,
                        "document_type": document_type,
                        "page_numbers": page_numbers,
                        "original_file_path": pdf_path,
                        "original_filename": doc.get("suggested_filename", "document"),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens
                    })
                    written_pages.update(page_numbers)
                    logger.info(f"Created: {output_path}")

            # --- Post-split verification: ensure all pages are present ---
            missing_after_split = sorted(list(all_pages - written_pages))
            if missing_after_split:
                logger.error(f"Pages missing after split: {missing_after_split}. Creating extra Unclassified Document PDF.")
                # Compose new filename
                doc_type_slug = "unclassified-document"
                page_numbers_str = "-".join(str(p) for p in missing_after_split)
                new_filename = f"{original_filename}_{doc_type_slug}_{page_numbers_str}"
                output_path = self.split_pdf_by_pages(
                    pdf_path,
                    (min(missing_after_split), max(missing_after_split)),
                    output_dir,
                    new_filename
                )
                if output_path:
                    output_files.append({
                        "filename": os.path.basename(output_path),
                        "path": output_path,
                        "document_type": "Unclassified Document (post-check)",
                        "page_numbers": missing_after_split,
                        "original_file_path": pdf_path,
                        "original_filename": "unclassified_document_post_check",
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens
                    })
                    logger.info(f"Created (post-check): {output_path}")

        except Exception as e:
            logger.error(f"Error splitting PDF documents: {e}")
        return output_files

    def store_token_usage(self, input_tokens, output_tokens, total_tokens, context=None):
        """Store token usage in MongoDB"""
        try:
            record = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "context": context
            }
            token_collection.insert_one(record)
            logger.info(f"Token usage stored in MongoDB: {record}")
        except Exception as e:
            logger.error(f"Error storing token usage in MongoDB: {e}")

    def split_pdfs_by_final_paths(self, final_paths: list) -> dict:
        """
        Splits PDFs as per the flat list of cut instructions (each with original_file_path, start_page, end_page, pdf_name, is_modify).
        Returns a dict with 'split_pdf_array' and 'errors'.
        Note: Deletion of old files is handled outside this function.
        """
        split_pdf_array = []
        errors = []
        for item in final_paths:
            try:
                original_file_path = item.get('original_file_path')
                start_page = int(item.get('start_page'))
                end_page = int(item.get('end_page'))
                pdf_name = item.get('pdf_name', 'section')
                is_modify = item.get('is_modify')
                # Accept both string and boolean for is_modify
                if isinstance(is_modify, str):
                    is_modify_bool = is_modify.lower() == 'true'
                else:
                    is_modify_bool = bool(is_modify)

                if not (original_file_path and start_page and end_page and pdf_name):
                    errors.append(f"Missing required fields in item: {item}")
                    continue

                if not os.path.exists(original_file_path):
                    errors.append(f"Original file not found: {original_file_path}")
                    continue

                # Prepare new file name
                original_base = os.path.splitext(os.path.basename(original_file_path))[0]
                folder = os.path.dirname(original_file_path)
                new_file_name = f"{original_base}_{pdf_name}_{start_page}_{end_page}.pdf"
                new_file_path = os.path.join(folder, new_file_name)

                # Split PDF
                with open(original_file_path, 'rb') as infile:
                    reader = PdfReader(infile)
                    total_pages = len(reader.pages)
                    if not (1 <= start_page <= end_page <= total_pages):
                        errors.append(f"Invalid page range {start_page}-{end_page} for file {original_file_path} (total pages: {total_pages})")
                        continue
                    writer = PdfWriter()
                    for p in range(start_page - 1, end_page):
                        writer.add_page(reader.pages[p])
                    with open(new_file_path, 'wb') as outfile:
                        writer.write(outfile)
                split_pdf_array.append(new_file_path)
            except Exception as e:
                errors.append(f"Error processing item {item}: {e}")
        return {"split_pdf_array": split_pdf_array, "errors": errors}

def get_args():
    """Parse command line arguments for subprocess interaction."""
    parser = argparse.ArgumentParser(description="Process folder and output results with timestamp.")
    parser.add_argument('input_folder_path', type=str, help='Path to the input folder (or JSON file with folder_path)')
    parser.add_argument('timestamp', type=str, help='Timestamp string for output file naming')
    args = parser.parse_args()
    return args.input_folder_path, args.timestamp


def process_folder_subprocess(input_json: dict, timestamp: str) -> str:
    """
    Subprocess entry point for frontend-backend interaction.
    input_json: dict loaded from JSON file, must contain 'folder_path'.
    timestamp: string for output file naming.
    Writes output to file and returns '1' as string on completion.
    """
    output = {}
    try:
        folder_path = input_json.get('folder_path')
        if not folder_path:
            raise ValueError('folder_path missing in input JSON')
        
        processor = DocumentProcessor()
        results = processor.process_folder(folder_path)
        
        # Transform results into the desired output format
        output_files_transformed = []
        input_tokens, output_tokens, total_tokens = None, None, None

        # Process successfully split multi-page PDFs
        for f in results.get('output_files', []):
            input_tokens = f.get('input_tokens')
            output_tokens = f.get('output_tokens')
            total_tokens = f.get('total_tokens')
            page_numbers = f.get('page_numbers', [])
            is_multipage = len(page_numbers) > 1
            
            file_info = {
                'original_file_path': f.get('original_file_path'),
                'path': f['path'],
                'is_multipage': is_multipage
            }
            if is_multipage:
                file_info['start_page'] = min(page_numbers)
                file_info['end_page'] = max(page_numbers)
            
            output_files_transformed.append(file_info)
        
        # Include skipped single-page PDFs and images in the output
        for skipped in results.get('skipped_files', []):
            if 'path' in skipped:
                output_files_transformed.append({
                    'original_file_path': skipped['path'],
                    'path': skipped['path'],
                    'is_multipage': False
                })

        # Store token usage in MongoDB
        processor.store_token_usage(
            input_tokens if input_tokens is not None else 0,
            output_tokens if output_tokens is not None else 0,
            total_tokens if total_tokens is not None else 0,
            context={"folder_path": folder_path, "timestamp": timestamp}
        )
        
        output = {
            "status": "success",
            "status_code": "200",
            "output_files": output_files_transformed,
            "input_tokens": input_tokens if input_tokens is not None else 0,
            "output_tokens": output_tokens if output_tokens is not None else 0,
            "total_tokens": total_tokens if total_tokens is not None else 0,
        }
        
    except Exception as e:
        output = {
            "status": "error",
            "status_code": "500",
            'error': str(e)
        }
    
    # Write the final transformed output to a file
    output_filename = f"file_{timestamp}.json"
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    
    return str(1)

# --- Removed Flask app initialization and route handlers ---

if __name__ == '__main__':
    """
    This block allows the script to be run from the command line,
    making it usable as a subprocess.
    """
    input_path, timestamp = get_args()
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
        # Call the processing function, which handles all output file writing
        process_folder_subprocess(input_data, timestamp)
    except Exception as e:
        # Write the actual error to the output file for transparency
        output = {
            "status": "error",
            "status_code": "500",
            'error': f"Failed to execute subprocess: {e}"
        }
        output_filename = f"file_{timestamp}.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
