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
            return jsonify({"error": "Subprocess failed", "details": str(e)}), 500
        # Read output JSON file
        output_filename = f"file_{timestamp}.json"
        if not os.path.exists(output_filename):
            return jsonify({"error": f"Output file not found: {output_filename}"}), 500
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
            "error": str(e),
            "status": "error"
        }), 500

if __name__ == '__main__':
    # Check if Gemini API key is set
    if GEMINI_API_KEY == 'your-gemini-api-key-here':
        print("⚠️  Warning: Please set your GEMINI_API_KEY environment variable")
        print("   export GEMINI_API_KEY='your-actual-api-key'")
    app.run(debug=True, host='0.0.0.0', port=5000) 