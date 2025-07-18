# PDF Document Splitter API

A Flask-based API that automatically analyzes and splits multi-page PDF documents into individual documents using Google's Gemini 2.5 Flash model.

## Features

- **Automatic Document Detection**: Uses Gemini AI to identify different document types within a multi-page PDF
- **Smart Splitting**: Splits PDFs based on AI analysis with suggested filenames
- **File Type Filtering**: Automatically skips image files and single-page PDFs
- **RESTful API**: Easy-to-use HTTP endpoints for processing
- **Structured Output**: Returns JSON responses with file paths, multipage info, and Gemini token usage
- **Token Usage Reporting**: Reports Gemini API input, output, and total token counts
- **Logging**: Logs all processing results to `processing.log`
- **Environment Variable Support**: Loads configuration from `.env` file

## Installation

### Prerequisites

- Python 3.8+
- Google Gemini API key

### Setup

1. **Clone or create the project directory:**
```bash
mkdir document-splitter
cd document-splitter
```

2. **Create a virtual environment:**
```bash
python -m venv venv
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Set up your Gemini API key:**
```bash
# Option 1: Set environment variable
export GEMINI_API_KEY='your-actual-gemini-api-key'

# Option 2: Create a .env file in the project root:
# .env
GEMINI_API_KEY=your-actual-gemini-api-key
```

## Usage

### Starting the Server

```bash
python pdf_splitter.py
```

The API will be available at `http://localhost:5000`

### API Endpoints

#### 1. Process Documents in Folder

**POST** `/process`

Process all documents in a specified folder path.

**Request Body:**
```json
{
    "folder_path": "/path/to/your/documents"
}
```

**Response:**
```json
{
    "status": "success",
    "output_files": [
        { "path": "/path/to/output/file1.pdf", "is_multipage": true },
        { "path": "/path/to/output/file2.pdf", "is_multipage": false },
        ...
    ],
    "input_tokens": 123,
    "output_tokens": 45,
    "total_tokens": 168
}
```
- `output_files` includes all split PDFs, skipped single-page PDFs, and skipped images, each with their file path and whether they are multipage.
- Token fields report Gemini API usage for the last processed file (or 0 if not applicable).
- All processing details are also logged to `processing.log`.

#### 2. Analyze Single PDF

**POST** `/analyze`

Analyze a single PDF file with Gemini (does not split).

**Request Body:**
```json
{
    "pdf_path": "/path/to/your/document.pdf"
}
```

**Response:**
```json
{
    "status": "success",
    "message": "Analysis completed",
    "analysis": {
        "documents": [
            {
                "document_type": "Aadhar Card",
                "page_numbers": [1, 2],
                "suggested_filename": "aadhar_card",
                "reason": "Contains Aadhar card header and UID format"
            }
        ],
        "total_pages": 5,
        "analysis_confidence": "high",
        "input_tokens": 123,
        "output_tokens": 45,
        "total_tokens": 168
    }
}
```

#### 3. Health Check

**GET** `/health`

Returns API health status.

**Response:**
```json
{
    "status": "healthy",
    "message": "API is running"
}
```

#### 4. API Info

**GET** `/`

Returns API info and available endpoints.

**Response:**
```json
{
    "message": "PDF Document Splitter API",
    "version": "1.0",
    "endpoints": {
        "/process": "POST - Process documents in a folder",
        "/health": "GET - Health check"
    }
}
```

### Example Usage with cURL

```bash
# Process documents in a folder
curl -X POST http://localhost:5000/process \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "/path/to/your/documents"}'

# Analyze a single PDF
curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"pdf_path": "/path/to/your/document.pdf"}'
```

### Example Usage with Python

```python
import requests

# Process documents in folder
response = requests.post(
    'http://localhost:5000/process',
    json={'folder_path': '/path/to/your/documents'}
)

result = response.json()
print(result)

# Get list of output files
output_files = result['output_files']
for file_info in output_files:
    print(f"Created: {file_info['path']} (Multipage: {file_info['is_multipage']})")
```

## Processing Flow

1. **Input**: Folder path containing documents
2. **Filtering**: 
   - Skip image files (PNG, JPG, etc.)
   - Skip single-page PDFs
   - Process multi-page PDFs only
3. **Analysis**: Send PDF to Gemini 2.5 Flash for document identification
4. **Splitting**: Split PDF based on AI analysis results
5. **Output**: Save individual documents with suggested filenames
6. **Logging**: All results are appended to `processing.log`

## Document Types Supported

The AI can identify various document types including:
- Aadhar Cards
- Passports
- Bank Statements
- Invoices
- Certificates
- Legal Documents
- And many more...

## Configuration

You can modify the following settings in `pdf_splitter.py`:

- `UPLOAD_FOLDER`: Directory for temporary files
- `PROCESSED_FOLDER`: Directory for processed files
- `ALLOWED_EXTENSIONS`: Supported file extensions
- `GEMINI_API_KEY`: Your Gemini API key (via environment or `.env`)

## Environment Variables

- `GEMINI_API_KEY`: Your Google Gemini API key (required)
- You can use a `.env` file in the project root for local development.

## Error Handling

The API provides comprehensive error handling:

- **File not found**: Returns 400 with error message
- **Invalid file type**: Skips with reason
- **API errors**: Returns 500 with error details
- **Processing errors**: Logged and returned in response

## Logging

The application uses Python's built-in logging module. Logs include:
- Processing status
- Error messages
- File operations
- API responses
- All processing results are appended to `processing.log`

## Security Considerations

- Input validation for file paths
- Secure filename generation
- Error message sanitization
- API key protection

## Implementation Details

- **PDF to Image Conversion**: Uses PyMuPDF (`fitz`) to convert PDF pages to images for Gemini analysis.
- **PDF Manipulation**: Uses PyPDF2 for reading and splitting PDFs.
- **AI Model**: Uses Gemini 2.5 Flash via the `google-generativeai` Python SDK.
- **Token Usage**: Reports Gemini API token usage in responses.
- **Environment Loading**: Uses `python-dotenv` to load environment variables from `.env`.

## Limitations

- Requires Google Gemini API key
- Processing time depends on PDF size and complexity
- Memory usage scales with PDF size
- API rate limits apply based on Gemini pricing

## Troubleshooting

### Common Issues

1. **"Invalid API key"**: Verify your Gemini API key is correct
2. **"File not found"**: Check file paths and permissions
3. **"Memory error"**: Reduce PDF size or increase system memory
4. **"Processing timeout"**: Large PDFs may take longer to process

### Debug Mode

Run with debug mode for detailed error messages:
```bash
python pdf_splitter.py
# Debug mode is enabled by default
```

## License

This project is provided as-is for educational and commercial use.

## Support

For issues and questions, please check the error logs and ensure all dependencies are properly installed.