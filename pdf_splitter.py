import os
import json
import base64
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

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
            # Convert PDF to images
            images = self.pdf_to_images(pdf_path)
            if not images:
                return {"error": "Failed to convert PDF to images"}
            # Prepare the prompt
            prompt = """
            Analyze this multi-page PDF document and identify different types of documents within it.
            For each document type you identify, provide:
            1. document_type: The type of document (e.g., "Aadhar Card", "Passport", "Bank Statement", "Invoice", etc.)
            2. page_numbers: Array of page numbers that belong to this document (1-indexed)
            3. suggested_filename: A clean filename for this document (without extension)
            4. reason: Brief explanation of why you identified this as this document type
            Return the response as a JSON object with this structure:
            {
                "documents": [
                    {
                        "document_type": "Document Type",
                        "page_numbers": [1, 2],
                        "suggested_filename": "document_name",
                        "reason": "Explanation of identification"
                    }
                ],
                "total_pages": number_of_pages,
                "analysis_confidence": "high/medium/low"
            }
            Be thorough in your analysis and look for:
            - Headers, logos, and official markings
            - Document structure and layout
            - Text content and formatting
            - Page continuity and relationships
            Ensure page numbers are accurate and don't overlap between different documents and don't skip any page.
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
        """Split PDF into individual documents based on analysis, propagate token info"""
        output_files = []
        try:
            documents = analysis_result.get("documents", [])
            # Get the original combined filename (without extension)
            original_filename = os.path.splitext(os.path.basename(pdf_path))[0]
            # Get token info from analysis_result
            input_tokens = analysis_result.get('input_tokens')
            output_tokens = analysis_result.get('output_tokens')
            total_tokens = analysis_result.get('total_tokens')
            for doc in documents:
                page_numbers = doc.get("page_numbers", [])
                suggested_filename = doc.get("suggested_filename", "document")
                document_type = doc.get("document_type", "Unknown")
                if not page_numbers:
                    continue
                # Slugify document_type: lowercase, replace spaces with hyphens
                doc_type_slug = secure_filename(document_type.lower().replace(' ', '-'))
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
                        "original_filename": suggested_filename,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens
                    })
                    logger.info(f"Created: {output_path}")
        except Exception as e:
            logger.error(f"Error splitting PDF documents: {e}")
        return output_files

# Initialize processor
processor = DocumentProcessor()

@app.route('/')
def index():
    return jsonify({
        "message": "PDF Document Splitter API",
        "version": "1.0",
        "endpoints": {
            "/process": "POST - Process documents in a folder",
            "/health": "GET - Health check"
        }
    })

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "message": "API is running"})

@app.route('/process', methods=['POST'])
def process_documents():
    """Process documents in the provided folder path"""
    try:
        data = request.get_json()
        if not data or 'folder_path' not in data:
            return jsonify({
                "error": "folder_path is required in request body"
            }), 400
        folder_path = data['folder_path']
        # Validate folder path
        if not os.path.exists(folder_path):
            return jsonify({
                "error": f"Folder path does not exist: {folder_path}"
            }), 400
        if not os.path.isdir(folder_path):
            return jsonify({
                "error": f"Path is not a directory: {folder_path}"
            }), 400
        # Process the folder
        logger.info(f"Processing folder: {folder_path}")
        results = processor.process_folder(folder_path)
        # Log the full results to a file for debugging
        with open('processing.log', 'a', encoding='utf-8') as log_file:
            log_file.write(json.dumps(results, indent=2))
            log_file.write('\n')
        # Prepare output file info
        output_files = []
        # For split PDFs (output_files)
        input_tokens = None
        output_tokens = None
        total_tokens = None
        for f in results.get('output_files', []):
            # Try to get token info from analysis if available
            input_tokens = f.get('input_tokens', None)
            output_tokens = f.get('output_tokens', None)
            total_tokens = f.get('total_tokens', None)
            # Determine is_multipage
            page_numbers = f.get('page_numbers', [])
            is_multipage = len(page_numbers) > 1 if page_numbers else None
            output_files.append({
                'path': f['path'],
                'is_multipage': is_multipage
            })
        # For images and single-page PDFs (skipped_files)
        for skipped in results.get('skipped_files', []):
            if skipped.get('reason', '').startswith('Image file') or skipped.get('reason', '').startswith('Single page PDF'):
                is_multipage = False
                output_files.append({
                    'path': skipped['path'],
                    'is_multipage': is_multipage
                })
        # Set top-level tokens to 0 if not set
        return jsonify({
            "status": "success",
            "output_files": output_files,
            "input_tokens": input_tokens if input_tokens is not None else 0,
            "output_tokens": output_tokens if output_tokens is not None else 0,
            "total_tokens": total_tokens if total_tokens is not None else 0
        })
    except Exception as e:
        logger.error(f"Error processing documents: {e}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@app.route('/analyze', methods=['POST'])
def analyze_single_pdf():
    """Analyze a single PDF file"""
    try:
        data = request.get_json()
        
        if not data or 'pdf_path' not in data:
            return jsonify({
                "error": "pdf_path is required in request body"
            }), 400
        
        pdf_path = data['pdf_path']
        
        # Validate PDF path
        if not os.path.exists(pdf_path):
            return jsonify({
                "error": f"PDF file does not exist: {pdf_path}"
            }), 400
        
        if not processor.is_pdf_file(pdf_path):
            return jsonify({
                "error": f"File is not a PDF: {pdf_path}"
            }), 400
        
        # Analyze the PDF
        logger.info(f"Analyzing PDF: {pdf_path}")
        analysis_result = processor.analyze_pdf_with_gemini(pdf_path)
        
        return jsonify({
            "status": "success",
            "message": "Analysis completed",
            "analysis": analysis_result
        })
        
    except Exception as e:
        logger.error(f"Error analyzing PDF: {e}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

if __name__ == '__main__':
    # Check if Gemini API key is set
    if GEMINI_API_KEY == 'your-gemini-api-key-here':
        print("⚠️  Warning: Please set your GEMINI_API_KEY environment variable")
        print("   export GEMINI_API_KEY='your-actual-api-key'")
    
    app.run(debug=True, host='0.0.0.0', port=5000)