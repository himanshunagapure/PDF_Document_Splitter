from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime, timezone
from pdf_splitter import DocumentProcessor, GEMINI_API_KEY
import logging
import subprocess
import tempfile
import sys

app = Flask(__name__)

# The processor is no longer used directly in the API file.
# processor = DocumentProcessor()

@app.route('/')
def index():
    return jsonify({
        "message": "PDF Document Splitter API",
        "version": "1.0",
        "endpoints": {
            "/process": "POST - Process documents in a folder",
            "/cut_pdf": "POST - Cut PDF by page numbers",
            "/health": "GET - Health check"
        }
    })

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "message": "API is running"})

@app.route('/process', methods=['POST'])
def process_documents():
    """Process documents in the provided folder path using subprocess."""
    try:
        data = request.get_json()
        if not data or 'folder_path' not in data:
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": "folder_path is required in request body"
            }), 400
        folder_path = data['folder_path']
        # Validate folder path
        if not os.path.exists(folder_path):
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": f"Folder path does not exist: {folder_path}"
            }), 400
        if not os.path.isdir(folder_path):
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": f"Path is not a directory: {folder_path}"
            }), 400
        # Prepare temp input JSON file
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as temp_input:
            json.dump({'folder_path': folder_path}, temp_input)
            temp_input_path = temp_input.name
        # Prepare timestamp
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        # Call subprocess to run process_folder_subprocess
        subprocess_cmd = [
            sys.executable, 'pdf_splitter.py', temp_input_path, timestamp
        ]
        try:
            subprocess.run(subprocess_cmd, check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Subprocess failed: {e}")
            return jsonify({
                "status": "error",
                "status_code": "500",
                "error": "Subprocess failed",
                "details": str(e)
            }), 500
        # Read output JSON file
        output_filename = f"file_{timestamp}.json"
        if not os.path.exists(output_filename):
            return jsonify({
                "status": "error",
                "status_code": "500",
                "error": f"Output file not found: {output_filename}"
            }), 500
        with open(output_filename, 'r', encoding='utf-8') as f:
            output_data = json.load(f)
        # Clean up temp files
        os.remove(temp_input_path)
        # Optionally, remove output file after reading
        # os.remove(output_filename)
        return jsonify(output_data)
    except Exception as e:
        logging.error(f"Error processing documents: {e}")
        return jsonify({
            "status": "error",
            "status_code": "500",
            "error": str(e)
        }), 500

@app.route('/cut_pdf', methods=['POST'])
def cut_pdf():
    """Cut a PDF file by page numbers."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": "Request body is required"
            }), 400
        
        # Validate required parameters
        required_fields = ['folder_path', 'start_page', 'end_page']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "status": "error",
                    "status_code": "400",
                    "error": f"{field} is required in request body"
                }), 400
        
        folder_path = data['folder_path']
        start_page = data['start_page']
        end_page = data['end_page']
        
        # Validate folder path
        if not os.path.exists(folder_path):
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": f"Folder path does not exist: {folder_path}"
            }), 400
        if not os.path.isdir(folder_path):
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": f"Path is not a directory: {folder_path}"
            }), 400
        
        # Validate page numbers
        if not isinstance(start_page, int) or not isinstance(end_page, int):
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": "start_page and end_page must be integers"
            }), 400
        
        if start_page < 1 or end_page < 1:
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": "Page numbers must be positive integers"
            }), 400
        
        if start_page > end_page:
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": "start_page must be less than or equal to end_page"
            }), 400
        
        # Find PDF files in the folder
        pdf_files = []
        for filename in os.listdir(folder_path):
            if filename.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(folder_path, filename))
        
        if not pdf_files:
            return jsonify({
                "status": "error",
                "status_code": "400",
                "error": "No PDF files found in the specified folder"
            }), 400
        
        # Process the first PDF file found
        pdf_path = pdf_files[0]
        
        # Create DocumentProcessor instance and cut the PDF
        processor = DocumentProcessor()
        output_path = processor.cut_pdf_by_page_numbers(pdf_path, start_page, end_page)
        
        if output_path is None:
            return jsonify({
                "status": "error",
                "status_code": "500",
                "error": "Failed to cut PDF file"
            }), 500
        
        return jsonify({
            "status": "success",
            "status_code": "200",
            "original_pdf": pdf_path,
            "cut_pdf_path": output_path,
            "start_page": start_page,
            "end_page": end_page,
            "message": f"Successfully cut PDF from page {start_page} to {end_page}"
        })
        
    except Exception as e:
        logging.error(f"Error cutting PDF: {e}")
        return jsonify({
            "status": "error",
            "status_code": "500",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    # Check if Gemini API key is set
    if GEMINI_API_KEY == 'your-gemini-api-key-here':
        print("⚠️  Warning: Please set your GEMINI_API_KEY environment variable")
        print("   export GEMINI_API_KEY='your-actual-api-key'")
    app.run(debug=True, host='0.0.0.0', port=5000) 