# PDF Document Splitter API

This project provides a powerful and intelligent solution for splitting large, multi-page PDF documents into individual, logically separated files. It uses the Google Gemini AI model to analyze the content of each page and determine the boundaries of different documents within a single PDF file.

The application is architected as a Python Flask API that can process entire folders of PDFs, making it easy to integrate into larger workflows.

## Architecture

The system is designed with a clean separation of concerns:

-   **`main_api.py`**: This is the front-facing web server built with Flask. It exposes the API endpoints, handles incoming requests, validates input, and manages the subprocess for processing.
-   **`pdf_splitter.py`**: This is the core processing engine. It contains all the logic for PDF analysis, interaction with the Gemini API, and file splitting. It is designed to be run as a standalone script via a subprocess, ensuring that heavy AI processing does not block the API server.

The API (`main_api.py`) communicates with the processing engine (`pdf_splitter.py`) by creating a temporary JSON file with the request details and invoking the script in a new process. The script then writes its output to a uniquely named JSON file, which the API reads and returns to the client.

## Features

-   **Intelligent Document Splitting**: Leverages Google Gemini to understand the content and context of each page.
-   **RESTful API**: Simple `POST` endpoint to process a folder of documents.
-   **Subprocess Architecture**: Ensures the API remains responsive during heavy processing tasks.
-   **MongoDB Integration**: Tracks Gemini API token usage (input, output, and total) for each processing job.
-   **Handles Mixed Content**: Correctly processes multi-page PDFs while identifying and skipping single-page PDFs and images (but still including them in the final report).
-   **Detailed JSON Output**: Provides a clean, structured JSON response with file paths, page counts, and token usage.

## Prerequisites

-   Python 3.8+
-   A running MongoDB instance
-   A Google Gemini API Key

## Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd document-splitter
    ```

2.  **Install the required Python packages:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Create an environment file:**
    Create a file named `.env` in the root of the project directory. This file will hold your secret keys and database configuration.

## Environment Variables

Your `.env` file must contain the following variables.

```ini
# Your Google Gemini API Key
GEMINI_API_KEY="your-gemini-api-key-here"

# Your MongoDB connection string
MONGO_URI="mongodb://localhost:27017/"

# The name of the MongoDB database to use
MONGO_DB="document_splitter"

# The name of the collection for storing token usage
MONGO_COLLECTION="token_usage"
```

## How to Run the API Server

Once your `.env` file is configured, you can start the Flask API server:

```bash
python main_api.py
```

The API will be available at `http://0.0.0.0:5000`.

## API Usage

### Process a Folder

-   **Endpoint**: `/process`
-   **Method**: `POST`
-   **Description**: Processes all valid files in the specified folder path.

#### Request Body

The request must be a JSON object containing the absolute path to the folder you want to process.

```json
{
    "folder_path": "D:\\path\\to\\your\\documents"
}
```

#### Success Response (`200 OK`)

If successful, the API returns a JSON object with the status, a list of all output files (both split and skipped), and the token usage for the transaction.

```json
{
    "status": "success",
    "status_code": "200",
    "output_files": [
        {
            "original_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101.pdf",
            "path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101_list-of-acceptable-documents_1.pdf",
            "is_multipage": false
        },
        {
            "original_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101.pdf",
            "path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101_employment-verification-form_2-3-4-5.pdf",
            "is_multipage": true,
            "start_page": 2,
            "end_page": 5
        },
        {
            "original_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101.pdf",
            "path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101_employment-screening-consent_6.pdf",
            "is_multipage": false
        },
        // ... more output files ...
    ],
    "input_tokens": 5980,
    "output_tokens": 1216,
    "total_tokens": 10449
}
```

#### Error Response

If an error occurs (e.g., folder not found, processing failure), the API will return a JSON object with an error message.

```json
{
    "status": "error",
    "status_code": "400",
    "error": "Folder path does not exist: D:\\path\\to\\non_existent_folder"
}
```

---

### Cut PDFs by Custom Page Ranges and Filenames

-   **Endpoint**: `/cut_pdf`
-   **Method**: `POST`
-   **Description**: Splits one or more PDFs according to a list of instructions (page ranges, filenames, etc). This is a direct, page-range-based cut (no AI analysis or document classification).

#### Request Body

The request must be a JSON object containing a `final_paths` key, which is a list of split instructions. Each instruction should be an object with the following fields:

-   `original_file_path`: Absolute path to the source PDF file.
-   `old_file_path`: Path to the file being split (can be same as original_file_path, or a temp file if chaining splits).
-   `start_page`: Starting page number (1-indexed, inclusive).
-   `end_page`: Ending page number (1-indexed, inclusive).
-   `pdf_name`: Name to use in the new split file (string, e.g. 'aadhar-card').
-   `is_modify`: Boolean or string ('true'/'false'). If true, deletes the old_file_path after splitting.

Example:

```json
{
    "final_paths": [
        {
            "original_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test1\\BGV - Mahendra Mahilange.pdf",
            "old_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test1\\BGV - Mahendra Mahilange.pdf",
            "start_page": 7,
            "end_page": 7,
            "pdf_name": "aadhar-card",
            "is_modify": false
        },
        {
            "original_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test1\\BGV - Mahendra Mahilange.pdf",
            "old_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test1\\BGV - Mahendra Mahilange.pdf",
            "start_page": 8,
            "end_page": 8,
            "pdf_name": "pan-card",
            "is_modify": false
        }
    ]
}
```

#### Success Response (`200 OK`)

If successful, the API returns a JSON object with the split file paths and any errors encountered:

```json
{
    "output": {
        "split_pdf_array": [
            "D:\\AIQoD\\Projects\\document-splitter\\solo_test1\\BGV - Mahendra Mahilange_aadhar-card_7_7.pdf",
            "D:\\AIQoD\\Projects\\document-splitter\\solo_test1\\BGV - Mahendra Mahilange_pan-card_8_8.pdf"
        ]
    }
}
```

If there are errors (e.g., invalid page range, missing file), they will be included in an `errors` array:

```json
{
    "output": {
        "split_pdf_array": [
            "D:\\AIQoD\\Projects\\document-splitter\\solo_test1\\BGV - Mahendra Mahilange_aadhar-card_7_7.pdf"
        ]
    },
    "errors": [
        "Invalid page range 100-200 for file D:\\AIQoD\\Projects\\document-splitter\\solo_test1\\BGV - Mahendra Mahilange.pdf (total pages: 24)"
    ]
}
```

#### Error Response

If the request is malformed (e.g., missing `final_paths`), the API will return an error message:

```json
{
    "status": "error",
    "status_code": "400",
    "error": "Request body must contain 'final_paths' key (list of split instructions)"
}
```

---

### Endpoint Comparison

-   **`/process`**: Uses Gemini AI to analyze and split all PDFs in a folder into logical documents, returning detailed file info and token usage.
-   **`/cut_pdf`**: Directly splits PDFs by custom page ranges and filenames (no AI), returning the new file paths. Token usage is not tracked for this endpoint.